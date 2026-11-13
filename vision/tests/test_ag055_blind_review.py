"""Blind-package software contracts, never agricultural performance fixtures."""
import json
import tempfile
import unittest
from pathlib import Path

from vision.ag055.blind_review import FIELDS,csv_bytes,date_valid,evaluate,html_form


class BlindReviewTests(unittest.TestCase):
    def test_review_date_requires_actual_timezone_not_naive_timestamp(self):
        self.assertFalse(date_valid(''))
        self.assertFalse(date_valid('2026-11-13T10:00:00'))
        self.assertTrue(date_valid('2026-11-13T10:00:00-05:00'))

    def test_blind_form_never_prefills_label_reviewer_date_or_source_id(self):
        record={k:'' for k in FIELDS};record.update(foto_id='F001',producto='mango',sha256_imagen='a'*64)
        html=html_form([record])
        self.assertNotIn('SEN_',html);self.assertNotIn('Alternaria',html)
        self.assertNotIn('scoresUncalibrated',html);self.assertNotIn('decisionScores',html)
        self.assertIn("['','E0','E1','E2','no_evaluable']",html)
        self.assertNotIn('Date.now',html)
        self.assertIn(r".join('\r\n')",html)
        csv=csv_bytes([record],FIELDS).decode('utf-8-sig')
        self.assertEqual(csv.splitlines()[1],'F001,mango,'+'a'*64+','*(len(FIELDS)-3))

    def test_changed_model_blocks_evaluation_before_any_human_data_or_inference(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'custodia').mkdir();(root/'models').mkdir()
            (root/'custodia/mapping.json').write_text('[]')
            (root/'custodia/protocol.json').write_text(json.dumps({'modelHashes':{'fake.json':'0'*64}}))
            (root/'models/fake.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'Frozen model changed'):
                evaluate(root,root,root/'absent.csv',root/'absent.csv',root,root/'output.json')
            self.assertFalse((root/'output.json').exists())
