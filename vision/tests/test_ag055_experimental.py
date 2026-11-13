"""Synthetic fixtures test contracts only; performance comes from external real runs."""
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

from vision.ag055.experimental import (audit_splits, describe, extract_verified, group_records,
                                      score, sha, split, train_task, validate_artifact)
from vision.ag055.review import save_review, train_reviewed


class ExperimentalTests(unittest.TestCase):
    def test_known_relations_are_transitive_and_duplicates_excluded(self):
        records = [{'id':str(i),'source':'SEN','relative':f'{i}.jpg',
                    'sha256':str(i),'pixelSha256':str(i)} for i in range(5)]
        records[4]['sha256'] = '0'
        records[4]['pixelSha256'] = '0'
        group_records(records,[{'imagen_a':'0','imagen_b':'1'},{'imagen_a':'1','imagen_b':'2'}])
        self.assertEqual(records[0]['group'],records[2]['group'])
        self.assertEqual(records[0]['group'],records[4]['group'])
        self.assertEqual(records[4]['excluded'],'duplicate_of:0')

    def test_temporal_and_filename_families_never_split(self):
        records = [{'id':str(i),'source':source,'relative':name,'sha256':str(i),'pixelSha256':str(i)}
                   for i,(source,name) in enumerate([('TQ','IMG_20230101_020000.jpg'),
                    ('TQ','20230101_090000.jpg'),('FG','Training/0/Aaa001.jpg'),('FG','Testing/9/Aaa076.jpg')])]
        group_records(records,[])
        self.assertEqual(records[0]['group'],records[1]['group'])
        self.assertEqual(records[2]['group'],records[3]['group'])

    def test_conflicting_exact_duplicate_labels_quarantine_both_members(self):
        rr=[{'id':'a','source':'FG','relative':'A01.jpg','sha256':'same','pixelSha256':'same','label':'2'},
            {'id':'b','source':'FG','relative':'A02.jpg','sha256':'same','pixelSha256':'same','label':'3'}]
        group_records(rr,[])
        self.assertTrue(all(r['excluded']=='conflicting_original_labels_exact_pixels' for r in rr))

    def samples(self):
        return [{'id':str(i),'group':str(i//2),'sha256':str(i),'pixelSha256':str(i),
                 'label':['Fresh','Rotten'][i%2]} for i in range(60)]

    def test_grouped_split_reproducible_and_leakage_rejected(self):
        records=self.samples(); other=self.samples()
        split(records,['Fresh','Rotten']); split(other,['Fresh','Rotten'])
        self.assertEqual([r['split'] for r in records],[r['split'] for r in other])
        audit_splits(records)
        records[1]['split']='test' if records[0]['split']!='test' else 'train'
        with self.assertRaisesRegex(ValueError,'Leakage'):
            audit_splits(records)

    def test_insufficient_groups_block(self):
        with self.assertRaisesRegex(ValueError,'Insufficient'):
            split(self.samples()[:4],['Fresh','Rotten'])

    def test_metric_confusion_and_zero_division(self):
        m=score([0,0,1,1],[0,1,1,1],['Fresh','Rotten'])
        self.assertEqual(m['confusionMatrix'],[[1,1],[0,2]])
        self.assertEqual(m['accuracy'],.75)
        self.assertAlmostEqual(m['precisionMacro'],5/6)
        self.assertAlmostEqual(m['recallMacro'],.75)
        self.assertAlmostEqual(m['f1Macro'],(2/3+.8)/2)
        self.assertEqual(score([0,1],[0,0],['a','b'])['perClass']['b']['precision'],0)

    def test_training_selects_on_validation_without_refitting_test(self):
        rr=self.samples(); features={r['id']:np.array([int(r['id'])%2,float(int(r['id'])//2)]) for r in rr}
        model,report=train_task(rr,['Fresh','Rotten'],features,55)
        self.assertIn(report['selectedOnValidation'],report['validation'])
        self.assertEqual(report['validation'][report['selectedOnValidation']]['f1Macro'],
                         max(v['f1Macro'] for v in report['validation'].values()))
        # Normalization fitted only on training rows, not validation/test.
        expected=np.stack([features[r['id']] for r in rr if r['split']=='train']).mean(0)
        np.testing.assert_allclose(model['mean'],expected)

    def test_reject_untrusted_label_space(self):
        with self.assertRaises(ValueError):
            validate_artifact({'version':'ag055-original-labels-v1','labels':['E0','E1','E2']})

    def test_roi_and_human_review_append_only(self):
        with tempfile.TemporaryDirectory(prefix='ag055-review-test-') as tmp:
            root=Path(tmp); out=io.BytesIO(); Image.new('RGB',(100,90),'red').save(out,format='PNG')
            raw=out.getvalue(); (root/'photo.png').write_bytes(raw)
            f,roi,method,pixel=describe(raw)
            self.assertEqual(len(f),57)
            with self.assertRaises(ValueError):
                describe(raw,[0,0,101,90])
            sample={'id':'test','source':'TQ','product':'tomate','relative':'photo.png','root':str(root),
                    'sha256':sha(raw),'pixelSha256':pixel,'group':'a','excluded':''}
            (root/'manifest.json').write_text(json.dumps([sample]),encoding='utf-8')
            payload={'id':'test','grade':'E1','reviewer':'TEST_ONLY','rubricVersion':'tomato-ext-test',
                     'evidence':'R03 synthetic software fixture','roi':roi,'roiConfirmed':True}
            first=save_review(root,payload); second=save_review(root,{**payload,'grade':'E2'})
            self.assertEqual(len(list((root/'reviews').glob('*.json'))),2)
            self.assertEqual(first['grade'],'E1'); self.assertEqual(second['grade'],'E2')
            self.assertFalse(first['accreditationVerified'])
            self.assertEqual((root/'photo.png').read_bytes(),raw)
            with self.assertRaises(ValueError):
                save_review(root,{**payload,'roiConfirmed':False})
            report=train_reviewed(root,root/'trained')
            self.assertEqual(report['products']['tomate']['status'],'blocked')

    def test_zip_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory(prefix='ag055-zip-test-') as tmp:
            p=Path(tmp)/'bad.zip'
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('../escape.txt','test')
            with self.assertRaisesRegex(ValueError,'Unsafe'):
                extract_verified(p,Path(tmp)/'unpacked')
            self.assertFalse((Path(tmp)/'escape.txt').exists())


if __name__=='__main__':
    unittest.main()
