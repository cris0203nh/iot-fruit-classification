import unittest
from acceptance_matrix import CASES, execute


class CIClosureMatrixTests(unittest.TestCase):
    def test_expected_cases_are_covered(self):
        names = {case[0] for case in CASES}
        self.assertTrue({'docs_only', 'complete_ci', 'backend_failure',
                         'security_failure', 'mandatory_skipped', 'unexpected_skip'} <= names)

    def test_matrix_matches_expected_outcomes(self):
        matrix = execute()
        self.assertTrue(matrix['all_match'])
        self.assertEqual(len(matrix['cases']), len(CASES))
        self.assertEqual(len({x['case'] for x in matrix['cases']}), len(CASES))

    def test_all_cases_marked_simulated(self):
        matrix = execute()
        self.assertTrue(all(item['simulated'] is True for item in matrix['cases']))

    def test_documentary_selection_is_empty(self):
        matrix = execute()
        doc = next(item for item in matrix['cases'] if item['case'] == 'docs_only')
        self.assertEqual(doc['selected'], [])

    def test_rejected_controls_cannot_turn_green(self):
        matrix = execute()
        rejected = {item['case'] for item in matrix['cases'] if item['actual'] == 'rejected'}
        self.assertEqual(rejected, {'backend_failure', 'security_failure',
                                    'mandatory_skipped', 'unexpected_skip', 'cancelled_module'})


if __name__ == '__main__':
    unittest.main()
