import json
import tempfile
import unittest
from copy import deepcopy
from datetime import date
from pathlib import Path
from unittest.mock import patch

from normalize import normalize, evaluate, run, except_npm_dev, NPM_EXCEPTION


class TestScanNormalizer(unittest.TestCase):
    def test_bandit_gate_high(self):
        data = {'results': [{'issue_severity': 'MEDIUM', 'test_id': 'B101', 'filename': 'demo.py', 'line_number': 1},
                            {'issue_severity': 'HIGH', 'test_id': 'B602', 'filename': 'api.py', 'line_number': 8}]}
        report = normalize('bandit', data)
        self.assertEqual(report['finding_count'], 2)
        self.assertEqual(evaluate(report, 'HIGH'), 1)
        self.assertEqual(evaluate({'finding_count': 1, 'findings': [report['findings'][0]]}, 'HIGH'), 0)

    def test_gitleaks_cannot_leak_raw_secret(self):
        raw = [{'RuleID': 'generic-api-key', 'File': 'src/config.py', 'StartLine': 1,
                'Secret': 'SUPER_SECRET_VALUE', 'Match': 'password=SUPER_SECRET_VALUE',
                'Email': 'private@example.test'}]
        sanitized = json.dumps(normalize('gitleaks', raw))
        self.assertNotIn('SUPER_SECRET_VALUE', sanitized)
        self.assertNotIn('private@example.test', sanitized)
        self.assertEqual(evaluate(normalize('gitleaks', raw), 'ANY'), 1)

    def test_zap_does_not_copy_request_or_url(self):
        report = normalize('zap', {'site': [{'@name': 'http://private', 'alerts': [
            {'pluginid': '10038', 'riskcode': '2', 'count': '4', 'instances': [
                {'uri': '/api/private?token=LEAKME', 'responseBody': 'LEAKME'}]}]}]})
        self.assertEqual(evaluate(report, 'HIGH'), 0)
        self.assertEqual(report['findings'][0]['occurrences'], 4)
        self.assertNotIn('LEAKME', json.dumps(report))

    def test_error_scanner_fails_closed_and_deletes_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'raw.json'
            out = Path(tmp) / 'report.json'
            src.write_text('{"Secret":"NEVER_UPLOAD"}')
            self.assertEqual(run(tool='gitleaks', source=src, output=out,
                                 exit_code=2, gate='ANY'), 2)
            self.assertFalse(src.exists())
            self.assertFalse(out.exists())

    def test_pip_and_npm_gate(self):
        pip = normalize('pip-audit', {'dependencies':[{'name':'demo', 'version':'1.0',
            'vulns':[{'id':'CVE-TEST'}]}]})
        self.assertEqual(evaluate(pip, 'ANY'), 1)
        npm = normalize('npm-audit', {'vulnerabilities': {'demo': {
            'severity':'moderate','isDirect':True}}})
        self.assertEqual(evaluate(npm, 'HIGH'), 0)
        self.assertEqual(evaluate(npm, 'MEDIUM'), 1)

    def test_gitleaks_empty_without_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp)/'raw.json', Path(tmp)/'report.json'
            self.assertEqual(run(tool='gitleaks',source=src,output=out,exit_code=0,gate='ANY'),0)
            self.assertEqual(json.loads(out.read_text())['finding_count'],0)

    def test_malformed_zap_or_npm_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize('zap', {'site': []})
        with self.assertRaises(ValueError):
            normalize('npm-audit', {'error': 'registry unavailable', 'vulnerabilities': {}})


class TestNpmTemporaryException(unittest.TestCase):
    def setUp(self):
        self.raw = {'vulnerabilities': {
            'picomatch': {'name': 'picomatch', 'severity': 'high', 'isDirect': False,
                         'nodes': ['node_modules/picomatch'], 'via': [{
                             'name': 'picomatch', 'dependency': 'picomatch', 'severity': 'high',
                             'url': 'https://github.com/advisories/' + NPM_EXCEPTION}]},
            'vite': {'name': 'vite', 'severity': 'high', 'isDirect': True,
                     'nodes': ['node_modules/vite'], 'via': ['picomatch']}}}
        self.lock = {'lockfileVersion': 3, 'packages': {
            'node_modules/picomatch': {'version': '4.0.7', 'dev': True},
            'node_modules/vite': {'version': '8.3.8', 'dev': True}}}

    def check(self, expected, *, today=date(2026, 11, 17)):
        report = normalize('npm-audit', self.raw)
        except_npm_dev(report, self.raw, self.lock, today=today)
        self.assertEqual(evaluate(report, 'HIGH'), expected)
        self.assertEqual(report['finding_count'], len(self.raw['vulnerabilities']))
        return report

    def test_exact_advisory_and_chain_are_reported_not_deleted(self):
        report = self.check(0)
        self.assertEqual(report['exception']['excepted_count'], 2)
        self.assertEqual(report['exception']['expires_utc'], '2026-12-01')
        self.assertTrue(all(f['exception'] == NPM_EXCEPTION for f in report['findings']))
        self.assertEqual(report['by_severity'], {'HIGH': 2})

    def test_expiry_blocks_on_first_december_and_after(self):
        self.check(0, today=date(2026, 11, 30))
        for day in (date(2026, 12, 1), date(2027, 1, 1)):
            self.assertEqual(self.check(1, today=day)['exception']['excepted_count'], 0)

    def test_different_advisory_on_same_package_blocks_entire_chain(self):
        self.raw['vulnerabilities']['picomatch']['via'].append({
            'name': 'picomatch', 'dependency': 'picomatch', 'severity': 'high',
            'url': 'https://github.com/advisories/GHSA-other'})
        self.assertEqual(self.check(1)['exception']['excepted_count'], 0)

    def test_unrelated_high_and_critical_still_block(self):
        for severity in ('high', 'critical'):
            self.raw['vulnerabilities']['other'] = {
                'name': 'other', 'severity': severity, 'via': [], 'nodes': []}
            self.assertEqual(self.check(1)['exception']['excepted_count'], 2)

    def test_parent_with_additional_cause_is_not_excepted(self):
        self.raw['vulnerabilities']['vite']['via'].append({'url': 'other'})
        self.assertEqual(self.check(1)['exception']['excepted_count'], 1)

    def test_raw_exception_markers_are_not_trusted(self):
        self.raw['vulnerabilities']['other'] = {
            'name': 'other', 'severity': 'critical', 'exception': NPM_EXCEPTION}
        self.check(1)
        report = {'tool': 'npm-audit', 'finding_count': 1,
                  'findings': [{'severity': 'CRITICAL', 'exception': 'arbitrary'}]}
        self.assertEqual(evaluate(report, 'HIGH'), 1)

    def test_critical_reclassification_of_same_advisory_is_not_excepted(self):
        self.raw['vulnerabilities']['picomatch']['severity'] = 'critical'
        self.check(1)

    def test_production_or_shared_nodes_block(self):
        original = deepcopy(self.lock)
        for name in ('picomatch', 'vite'):
            self.lock = deepcopy(original)
            self.lock['packages']['node_modules/' + name].pop('dev')
            self.check(1)
        self.lock = deepcopy(original)
        self.lock['packages']['node_modules/prod/node_modules/picomatch'] = {'version': '4.0.7'}
        self.check(1)

    def test_missing_nodes_unverified_versions_and_cycles_block(self):
        original = deepcopy(self.raw)
        for change in ('missing-node', 'version', 'cycle', 'missing-reference', 'empty-via'):
            self.raw = deepcopy(original)
            self.lock['packages']['node_modules/picomatch']['version'] = '4.0.7'
            if change == 'missing-node':
                self.raw['vulnerabilities']['picomatch']['nodes'] = ['node_modules/unknown']
            elif change == 'version':
                self.lock['packages']['node_modules/picomatch']['version'] = '4.0.8'
            elif change == 'cycle':
                self.raw['vulnerabilities']['picomatch']['via'] = ['vite']
            elif change == 'missing-reference':
                self.raw['vulnerabilities']['picomatch']['via'] = ['absent']
            else:
                self.raw['vulnerabilities']['picomatch']['via'] = []
            with self.subTest(change=change):
                self.check(1)

    def run_report(self, raw, code, *, exception=True):
        with tempfile.TemporaryDirectory() as tmp:
            src, out, lock = (Path(tmp)/name for name in ('raw.json', 'out.json', 'lock.json'))
            src.write_text(json.dumps(raw), encoding='utf-8')
            lock.write_text(json.dumps(self.lock), encoding='utf-8')
            out.write_text('stale result', encoding='utf-8')
            with patch('normalize.except_npm_dev', wraps=lambda report, raw, lock:
                       except_npm_dev(report, raw, lock, today=date(2026, 11, 17))):
                result = run(tool='npm-audit', source=src, output=out, exit_code=code,
                             gate='ANY', npm_dev_exception_lock=lock if exception else None)
            self.assertFalse(src.exists())
            if result == 2:
                self.assertFalse(out.exists())
            return result

    def test_scan_errors_and_contradictory_exit_codes_cannot_be_excepted(self):
        self.assertEqual(self.run_report(self.raw, 2), 2)
        self.assertEqual(self.run_report(self.raw, 0), 2)
        self.assertEqual(self.run_report({'vulnerabilities': {}}, 1), 2)
        self.assertEqual(self.run_report({'error': 'registry failed', **self.raw}, 1), 2)
        self.assertEqual(self.run_report({'invalid': True}, 1), 2)

    def test_missing_or_invalid_lock_is_scan_error(self):
        for lock in ({}, {'lockfileVersion': 2, 'packages': {}},
                     {'lockfileVersion': 3, 'packages': {'node_modules/picomatch': None}}):
            self.lock = lock
            self.assertEqual(self.run_report(self.raw, 1), 2)

    def test_production_audit_without_option_has_no_exception_even_for_known_advisory(self):
        self.assertEqual(self.run_report(self.raw, 1, exception=False), 1)
        self.assertEqual(self.run_report({'vulnerabilities': {}}, 0, exception=False), 0)
        self.assertEqual(self.run_report(self.raw, 1), 0)
