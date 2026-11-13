"""Synthetic contract fixtures; never evidence of agricultural model performance."""
import json
import tempfile
import unittest
from pathlib import Path

from vision.ag055.uncertainty import VERSION, assess, fit_policy, load_policy


class UncertaintyTests(unittest.TestCase):
    def test_validation_threshold_targets_rotten_review_and_never_calibrates(self):
        scores=[[.99,.01],[.95,.05],[.8,.2],[.6,.4],[.3,.7],[.1,.9]]*5
        truth=[0,1,0,1,1,1]*5
        p=fit_policy(scores,truth,['Fresh','Rotten'])
        self.assertEqual(p['validationCount'],30)
        self.assertGreaterEqual(p['validationRottenReviewRecall'],.95)
        result=assess({'task':'TQ','label':'Fresh','scoresUncalibrated':{'Fresh':.95,'Rotten':.05}},p)
        self.assertIn('potential_rotten_prioritize_review',result['reasons'])
        self.assertFalse(result['confidenceCalibrated'])
        self.assertTrue(result['humanReviewRequired'])
        self.assertFalse(result['operationalUseAllowed'])

    def test_unavailable_policy_fails_to_review_and_fgrade_is_diagnostic(self):
        p={'task':'SEN','label':'Healthy','scoresUncalibrated':{'Healthy':.99,'Disease':.01}}
        self.assertEqual(assess(p)['priority'],'priority')
        self.assertEqual(assess({**p,'task':'FG'})['priority'],'diagnostic_only')
        with self.assertRaises(ValueError):
            fit_policy([[.9,.1]]*10,[0]*10,['Fresh','Rotten'])

    def test_policy_requires_matching_model_data_and_validation_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'policy.json'
            payload={'version':VERSION,'testUsedForThresholdSelection':False,'thresholdSelectionSplit':'validation',
                'tasks':{'TQ':{'split':'validation','modelSha256':'abc','dataVersion':'data',
                               'marginThreshold':.4,'rottenReviewThreshold':.1}}}
            file.write_text(json.dumps(payload))
            self.assertIsNotNone(load_policy(file,'TQ','abc','data'))
            self.assertIsNone(load_policy(file,'TQ','wrong','data'))
            self.assertIsNone(load_policy(file,'TQ','abc','wrong'))
            payload['testUsedForThresholdSelection']=True
            file.write_text(json.dumps(payload))
            self.assertIsNone(load_policy(file,'TQ','abc','data'))
