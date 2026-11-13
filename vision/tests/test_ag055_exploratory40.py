"""Software contracts with synthetic records, never measured agricultural results."""
import unittest

from vision.ag055.exploratory40 import match_reviews, metrics


class Exploratory40Tests(unittest.TestCase):
    def setUp(self):
        self.mapping = [dict(foto_id='F001', product='mango', sha256='a'*64),
                        dict(foto_id='F002', product='tomate', sha256='b'*64)]
        self.human = [dict(foto_id=m['foto_id'], producto=m['product'], sha256_imagen=m['sha256'],
                           grado_humano='E1', revisor_id='', fecha_revision_iso='') for m in self.mapping]

    def test_matches_by_id_with_blank_independence_and_reviewer_metadata(self):
        result = match_reviews(self.mapping, list(reversed(self.human)))
        self.assertEqual([h['foto_id'] for m, h in result], ['F001', 'F002'])
        self.assertEqual(self.human[0]['revisor_id'], '')

    def test_duplicate_or_missing_or_unknown_ids_rejected(self):
        for rows in ([self.human[0]]*2, self.human[:1],
                     [self.human[0], {**self.human[1], 'foto_id': 'F099'}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                match_reviews(self.mapping, rows)

    def test_changed_sha_or_product_rejected(self):
        for key, value in [('producto', 'tomate'), ('sha256_imagen', 'c'*64)]:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'Fixed review columns'):
                match_reviews(self.mapping, [{**self.human[0], key: value}, self.human[1]])

    def test_unknown_or_missing_grades_never_invented(self):
        for value in ('', 'Fresh', 'E3'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'human grade'):
                match_reviews(self.mapping, [{**self.human[0], 'grado_humano': value}, self.human[1]])

    def test_human_no_evaluable_preserved(self):
        result = match_reviews(self.mapping, [{**self.human[0], 'grado_humano': 'no_evaluable'}, self.human[1]])
        self.assertEqual(result[0][1]['grado_humano'], 'no_evaluable')

    def test_confusion_orientation_and_macro_include_all_three_classes(self):
        result = metrics([dict(humanGrade=h, prediction={'label': p})
                          for h, p in [('E0', 'E0'), ('E0', 'E1'), ('E1', 'E1'), ('E2', 'E0')]])
        self.assertEqual(result['confusionMatrix'], [[1,1,0],[0,1,0],[1,0,0]])
        self.assertEqual(result['accuracy'], .5)
        self.assertAlmostEqual(result['f1Macro'], (0.5+2/3)/3)
        self.assertIsNone(metrics([]))


if __name__ == '__main__':
    unittest.main()
