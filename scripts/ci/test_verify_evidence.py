import copy
import unittest
from check_gate import MODULES, MANDATORY, build_report
from verify_evidence import verify


def fixture(*, selected=True):
    flags = {name: 'true' if selected else 'false' for name in MODULES}
    results = {name: 'success' for name in MANDATORY}
    results.update({name: 'success' if selected else 'skipped' for name in MODULES})
    return build_report(flags, results, metadata={
        'run_id': '1234', 'sha': 'a'*40, 'event': 'pull_request'})


class EvidenceAcceptanceTests(unittest.TestCase):
    def test_real_shape_full_selection(self):
        self.assertTrue(verify(fixture()))

    def test_valid_documentary_skips(self):
        self.assertTrue(verify(fixture(selected=False)))

    def test_valid_rejected_report_is_not_a_pass(self):
        report = fixture()
        report['checks'][3]['result'] = 'failure'
        report['checks'][3]['compliant'] = False
        report['counts']['noncompliant'] = 1
        report['decision'] = 'rejected'
        report['violations'] = ['backend: esperado=success, observado=failure']
        self.assertTrue(verify(report))
        self.assertEqual(report['decision'], 'rejected')

    def test_rejects_status_tampering(self):
        report = fixture()
        report['checks'][3]['result'] = 'failure'
        self.assertFalse(verify(report))

    def test_rejects_fake_approved_decision(self):
        report = fixture()
        report['decision'] = 'rejected'
        self.assertFalse(verify(report))

    def test_rejects_missing_module(self):
        report = fixture()
        report['checks'].pop()
        self.assertFalse(verify(report))

    def test_rejects_duplicate_module(self):
        report = fixture()
        report['checks'][4] = copy.deepcopy(report['checks'][3])
        self.assertFalse(verify(report))

    def test_rejects_forged_counts(self):
        report = fixture(selected=False)
        report['counts']['expected_skips'] = 0
        self.assertFalse(verify(report))

    def test_rejects_invalid_metadata(self):
        report = fixture()
        report['context']['sha'] = 'sensitive-access-token'
        self.assertFalse(verify(report))

    def test_rejects_unexpected_field(self):
        report = fixture()
        report['private_url'] = 'https://example.org/private?token=redacted'
        self.assertFalse(verify(report))

    def test_rejects_unknown_state(self):
        report = fixture()
        report['checks'][3]['result'] = 'neutral'
        self.assertFalse(verify(report))

    def test_rejects_non_json_objects(self):
        for item in (None, [], 'approved', 1):
            with self.subTest(item=item):
                self.assertFalse(verify(item))

    def test_rejects_bool_schema(self):
        report = fixture()
        report['schema_version'] = True
        self.assertFalse(verify(report))

    def test_rejects_nested_extra_metadata(self):
        report = fixture()
        report['context']['actor_email'] = 'example@example.invalid'
        self.assertFalse(verify(report))

    def test_rejects_inconsistent_selection(self):
        report = fixture(selected=False)
        report['checks'][3]['selection'] = 'selected'
        self.assertFalse(verify(report))

    def test_rejects_added_check_key(self):
        report = fixture()
        report['checks'][0]['secret'] = 'should-never-be-emitted'
        self.assertFalse(verify(report))


if __name__ == '__main__':
    unittest.main()
