"""LOCAL E2E fixture: isolated database/files and explicitly automated review events.

Run with original Python, PYTHONPATH pointing to backend and its site-packages.
Never connects to or migrates the user's database. No inference mocks.
"""
import hashlib
import json
import os
import sys
import shutil
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db
from app.models import Evaluation, Image, Lot, Role, User
from app.security import hash_password
from vision.ag055.experimental import private, predict

root=private(Path(os.environ['AG055_I04_EVIDENCE']))
data=root/'data'; data.mkdir(exist_ok=True)
(data/'images').mkdir(exist_ok=True)
review=root/'review_queue'; review.mkdir(exist_ok=True)
os.environ['AGROSCAN_REVIEW_RUN']=str(review)
os.environ['AGROSCAN_TEST_INSTANCE']='1'
run=Path(os.environ['AG055_REAL_RUN'])
os.environ['AGROSCAN_EXPLORATORY_MODELS_PATH']=str(run/'models')
os.environ['AGROSCAN_UNCERTAINTY_POLICY_PATH']=os.getenv('AG055_FROZEN_POLICY',str(root/'uncertainty_policy.json'))
pilot_run=Path(os.environ['AG055_PILOT117_RUN']) if os.getenv('AG055_PILOT117_RUN') else None
v2_run=Path(os.environ['AG055_V2_RUN']) if os.getenv('AG055_V2_RUN') else None
if v2_run:
    os.environ['AGROSCAN_V2_MODELS_PATH']=str(v2_run/'models')
if pilot_run:
    os.environ['AGROSCAN_PILOT117_MODELS_PATH']=str(pilot_run/'models')
    if not (review/'manifest.json').exists():
        shutil.copyfile(pilot_run/'manifest.json',review/'manifest.json')
        shutil.copytree(pilot_run/'reviews',review/'reviews')

@app.get('/_ag055_test_instance')
def fixture_identity():
    return {'instanceType':'isolated_ag055_e2e','automatedAnnotationsOnly':True}
for name,module in list(sys.modules.items()):
    if name.startswith('app.routers.') and hasattr(module,'DATA_DIR'):
        module.DATA_DIR=data
    if name=='app.routers.images':
        module.IMAGES_DIR=data/'images'
engine=create_engine(f'sqlite:///{data / "test.sqlite"}',connect_args={'check_same_thread':False})
Base.metadata.create_all(engine)
Session=sessionmaker(bind=engine)
def isolated_db():
    with Session() as db:
        yield db
app.dependency_overrides[get_db]=isolated_db
app.add_middleware(__import__('fastapi.middleware.cors',fromlist=['CORSMiddleware']).CORSMiddleware,
    allow_origins=['http://127.0.0.1:5174'],allow_methods=['*'],allow_headers=['*'])
with Session() as db:
    if not db.query(User).first():
        for role in ('operador','revisor'):
            db.add(User(username='i04_'+role,full_name='AUTOMATED E2E TEST ONLY',
                password_hash=hash_password(os.environ['AG055_TEST_PASSWORD']),
                is_active=True,roles=[Role(name=role)]))
        manifest=json.loads((run/'manifest.json').read_text(encoding='utf-8'))
        artifact=json.loads((run/'models/ag055_exploratory_TQ.json').read_text(encoding='utf-8'))
        samples=[r for r in manifest if r['source']=='TQ' and r.get('split')=='test' and r['label']=='Rotten']
        sample=next(r for r in samples if predict(artifact,(Path(r['root'])/r['relative']).read_bytes())['label']=='Fresh')
        pilot_records=json.loads((pilot_run/'manifest.json').read_text(encoding='utf-8')) if pilot_run else []
        if pilot_run:
            sample=next(r for r in pilot_records if r['product']=='tomate')
        raw=(Path(sample['root'])/sample['relative']).read_bytes()
        lot=Lot(code='I04-E2E',product='tomate',status='open',responsible='TEST ONLY')
        db.add(lot);db.flush()
        for piece in ('REAL-FALSE-NEGATIVE','NO-PHOTOGRAPH'):
            ev=Evaluation(lot_id=lot.id,piece_id=piece,product='tomate',image_count=1 if piece.startswith('REAL') else 0)
            db.add(ev);db.flush()
            if piece.startswith('REAL'):
                (data/'images/real.jpg').write_bytes(raw)
                db.add(Image(evaluation_id=ev.id,view='vista-1',relative_path='images/real.jpg',
                    content_type='image/jpeg',size_bytes=len(raw),idempotency_key=hashlib.sha256(raw).hexdigest()))
        if pilot_run:
            mango=next(r for r in pilot_records if r['product']=='mango')
            mango_raw=(Path(mango['root'])/mango['relative']).read_bytes()
            mango_lot=Lot(code='PILOT117-MANGO',product='mango',status='open',responsible='TEST ONLY')
            db.add(mango_lot);db.flush()
            ev=Evaluation(lot_id=mango_lot.id,piece_id='PILOT117-MANGO',product='mango',image_count=1)
            db.add(ev);db.flush();(data/'images/mango.jpg').write_bytes(mango_raw)
            db.add(Image(evaluation_id=ev.id,view='vista-1',relative_path='images/mango.jpg',content_type='image/jpeg',
                size_bytes=len(mango_raw),idempotency_key=hashlib.sha256(mango_raw).hexdigest()))
        if v2_run:
            records=json.loads((v2_run/'manifest.json').read_text(encoding='utf-8'))
            rejected=next(r for r in records if not r['evaluable'])
            rejected_raw=(Path(rejected['root'])/rejected['relative']).read_bytes()
            rejected_lot=Lot(code='V2-REJECTED',product=rejected['product'],status='open',responsible='TEST ONLY')
            db.add(rejected_lot);db.flush()
            ev=Evaluation(lot_id=rejected_lot.id,piece_id='V2-REJECTED-REAL-PHOTO',product=rejected['product'],image_count=1)
            db.add(ev);db.flush();(data/'images/v2-rejected.jpg').write_bytes(rejected_raw)
            db.add(Image(evaluation_id=ev.id,view='vista-1',relative_path='images/v2-rejected.jpg',content_type='image/jpeg',
                size_bytes=len(rejected_raw),idempotency_key=hashlib.sha256(rejected_raw).hexdigest()))
        db.commit()
        (root/'real_photo_provenance.json').write_text(json.dumps({'imageId':sample['id'],
            'originalLabel':sample['label'],'sha256':hashlib.sha256(raw).hexdigest(),
            'usage':'automated functional test; not a human annotation'},indent=2),encoding='utf-8')
