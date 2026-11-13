"""Final acceptance regressions: isolated synthetic fixtures, not human annotations."""
import json
import unittest
from unittest.mock import patch

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.quality_prediction_models import QualityPrediction
from app.routers import quality_prediction as router
import test_ag055_i04 as i04
from vision.ag055 import review


class I05AuditTests(unittest.TestCase):
    setUp=i04.I04Tests.setUp
    auth=i04.I04Tests.auth
    artifact=i04.I04Tests.artifact
    setup_review=i04.I04Tests.setup_review

    def test_partial_storage_write_does_not_publish_or_poison_history(self):
        body=self.setup_review()
        first=self.client.post(self.base+'/reviews',json=body,headers=self.auth()).json()
        before={p.name:p.read_bytes() for p in (self.dir/'reviews').glob('*.json')}
        def disk_full(payload, stream, **kwargs):
            stream.write('{"partial":')
            raise OSError('simulated full disk')
        with patch.object(review.json,'dump',side_effect=disk_full):
            response=self.client.post(self.base+'/reviews',json={**body,'expectedLastEventId':first['eventId']},headers=self.auth())
        self.assertEqual(response.status_code,503,response.text)
        self.assertEqual({p.name:p.read_bytes() for p in (self.dir/'reviews').glob('*.json')},before)
        self.assertEqual(self.client.get(self.base+'/reviews',headers=self.auth()).status_code,200)
        # Retry after recovery appends exactly one correction.
        response=self.client.post(self.base+'/reviews',json={**body,'expectedLastEventId':first['eventId']},headers=self.auth())
        self.assertEqual(response.status_code,201,response.text)
        self.assertEqual(len(list((self.dir/'reviews').glob('*.json'))),2)

    def test_unreadable_history_is_503_and_never_rewritten(self):
        body=self.setup_review()
        (self.dir/'reviews').mkdir()
        broken=self.dir/'reviews/broken.json'; broken.write_text('{partial')
        response=self.client.get(self.base+'/reviews',headers=self.auth())
        self.assertEqual(response.status_code,503,response.text)
        response=self.client.post(self.base+'/reviews',json=body,headers=self.auth())
        self.assertEqual(response.status_code,503,response.text)
        self.assertEqual(broken.read_text(),'{partial')

    def test_same_size_photo_change_rejected_before_new_inference(self):
        self.setup_review()
        path=self.dir/'images/1.jpg'; raw=path.read_bytes()
        # JFIF density metadata: valid JPEG, same byte length, different SHA-256.
        changed=bytearray(raw); changed[13]^=1; path.write_bytes(changed)
        response=self.client.post(self.base+'/exploratory/analyze',headers=self.auth())
        self.assertEqual(response.status_code,409,response.text)
        with self.Session() as db:
            self.assertEqual(db.query(QualityPrediction).count(),1)

    def test_database_write_failure_rolls_back_and_returns_503(self):
        self.setup_review()
        with self.Session() as db:
            db.query(QualityPrediction).delete(); db.commit()
        with patch.object(Session,'commit',side_effect=OperationalError('commit',{},Exception('disk unavailable'))):
            response=self.client.post(self.base+'/exploratory/analyze',headers=self.auth())
        self.assertEqual(response.status_code,503,response.text)
        with self.Session() as db:
            self.assertEqual(db.query(QualityPrediction).count(),0)
        self.assertEqual(self.client.post(self.base+'/exploratory/analyze',headers=self.auth()).status_code,200)

    def test_photo_permission_error_is_503_without_path_disclosure(self):
        self.setup_review()
        with patch.object(router.Path,'read_bytes',side_effect=PermissionError('PRIVATE_PATH')):
            response=self.client.get(self.base+'/reviews',headers=self.auth())
        self.assertEqual(response.status_code,503,response.text)
        self.assertNotIn('PRIVATE_PATH',response.text)


if __name__=='__main__':
    unittest.main()
