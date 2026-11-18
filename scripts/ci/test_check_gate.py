import unittest
from check_gate import MODULES, MANDATORY, validate


def all_ok():
    return ({name: 'true' for name in MODULES},
            {name: 'success' for name in (*MANDATORY, *MODULES)})


class GateTests(unittest.TestCase):
    def test_full_success(self):
        flags, results = all_ok()
        self.assertEqual(validate(flags, results), [])

    def test_documentation_only_expected_skips_are_safe(self):
        flags, results = all_ok()
        for name in MODULES:
            flags[name] = 'false'
            results[name] = 'skipped'
        self.assertEqual(validate(flags, results), [])

    def test_required_job_failure_is_blocked(self):
        flags, results = all_ok()
        results['backend'] = 'failure'
        self.assertTrue(validate(flags, results))

    def test_required_job_skipped_is_blocked(self):
        flags, results = all_ok()
        results['vision'] = 'skipped'
        self.assertTrue(validate(flags, results))

    def test_unexpected_success_in_skipped_job_is_mismatch(self):
        flags, results = all_ok()
        flags['backend'] = 'false'
        self.assertTrue(validate(flags, results))

    def test_non_selected_failed_job_is_blocked(self):
        flags, results = all_ok()
        flags['backend'] = 'false'
        results['backend'] = 'failure'
        self.assertTrue(validate(flags, results))

    def test_security_is_never_optional(self):
        flags, results = all_ok()
        results['seguridad'] = 'skipped'
        self.assertTrue(validate(flags, results))

    def test_invalid_or_missing_decision_is_blocked(self):
        flags, results = all_ok()
        flags['iot'] = ''
        self.assertTrue(validate(flags, results))

    def test_failed_detection_is_blocked(self):
        flags, results = all_ok()
        results['cambios'] = 'failure'
        self.assertTrue(validate(flags, results))

    def test_cancellation_never_approves(self):
        flags, results = all_ok()
        results['integracion'] = 'cancelled'
        self.assertTrue(validate(flags, results))


if __name__ == '__main__':
    unittest.main()
