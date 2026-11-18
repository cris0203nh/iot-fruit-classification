import json
import tempfile
import unittest
from pathlib import Path

from normalize import normalize, evaluate, run


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
