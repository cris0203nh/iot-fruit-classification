import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from check_gate import MANDATORY, MODULES, build_report, main, markdown


def all_ok():
    flags = {name: 'true' for name in MODULES}
    results = {name: 'success' for name in (*MANDATORY, *MODULES)}
    return flags, results


class ReportTests(unittest.TestCase):
    def test_schema_complete_success(self):
        flags, results = all_ok()
        report = build_report(flags, results, metadata={
            'sha': 'f' * 40, 'event': 'pull_request', 'run_id': '12345'})
        self.assertEqual(report['decision'], 'approved')
        self.assertEqual(report['schema_version'], 1)
        self.assertEqual(len(report['checks']), len(MANDATORY) + len(MODULES))
        self.assertEqual(report['counts']['selected_modules'], 6)
        self.assertEqual(report['context']['run_id'], '12345')
        self.assertEqual(report['violations'], [])

    def test_expected_skips_appear_but_do_not_claim_execution(self):
        flags, results = all_ok()
        for name in MODULES:
            flags[name] = 'false'
            results[name] = 'skipped'
        report = build_report(flags, results)
        self.assertEqual(report['decision'], 'approved')
        self.assertEqual(report['counts']['expected_skips'], 6)
        self.assertIn('skipped', markdown(report))
        self.assertIn('Los módulos omitidos no se consideran ejecutados.', markdown(report))

    def test_selected_failure_is_rejected_and_reported(self):
        flags, results = all_ok()
        results['iot'] = 'failure'
        report = build_report(flags, results)
        self.assertEqual(report['decision'], 'rejected')
        self.assertEqual(report['violations'], ['iot: esperado=success, observado=failure'])

    def test_security_is_always_mandatory(self):
        flags, results = all_ok()
        results['seguridad'] = 'skipped'
        self.assertEqual(build_report(flags, results)['decision'], 'rejected')

    def test_malicious_environment_values_cannot_enter_report(self):
        flags, results = all_ok()
        secret = 'TOKEN_NOT_TO_EXPORT\n| forged | yes |'
        flags['backend'] = secret
        results['seguridad'] = secret
        report = build_report(flags, results, metadata={'sha': secret, 'run_id': secret, 'event': secret})
        combined = json.dumps(report) + markdown(report)
        self.assertNotIn(secret, combined)
        self.assertNotIn('TOKEN_NOT_TO_EXPORT', combined)
        self.assertEqual(report['context']['event'], 'unknown')
        self.assertIsNone(report['context']['sha'])
        self.assertEqual(report['decision'], 'rejected')

    def test_main_writes_report_and_summary_even_on_failed_job(self):
        flags, results = all_ok()
        results['backend'] = 'failure'
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp)/'reports'/'ci.json'
            summary = Path(tmp)/'summary.md'
            env = {f'SELECT_{k.upper()}':v for k,v in flags.items()}
            env.update({f'RESULT_{k.upper()}':v for k,v in results.items()})
            env.update({'CI_REPORT_PATH':str(artifact), 'GITHUB_STEP_SUMMARY':str(summary),
                        'GITHUB_EVENT_NAME':'pull_request', 'GITHUB_RUN_ID':'98765'})
            with patch.dict(os.environ, env, clear=True):
                self.assertEqual(main(), 1)
            self.assertEqual(json.loads(artifact.read_text(encoding='utf-8'))['decision'], 'rejected')
            self.assertIn('REJECTED', summary.read_text(encoding='utf-8').upper())

    def test_main_fails_closed_when_artifact_cannot_be_written(self):
        flags, results = all_ok()
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / 'existing-dir'
            artifact.mkdir()
            env = {f'SELECT_{k.upper()}':v for k,v in flags.items()}
            env.update({f'RESULT_{k.upper()}':v for k,v in results.items()})
            env['CI_REPORT_PATH'] = str(artifact)
            with patch.dict(os.environ, env, clear=True):
                self.assertEqual(main(), 1)


if __name__ == '__main__':
    unittest.main()
