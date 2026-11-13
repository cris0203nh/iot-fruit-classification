"""AG-055 I01: propuesta experimental E0/E1/E2, siempre sujeta a revisión.

No sustituye la decisión humana, no cambia visual_category ni ev.status,
no permite un modelo sin evidencia, ni confunde YOLOE con un clasificador.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, Field

from ..database import DATA_DIR, get_db
from ..dependencies import require_authenticated, require_operator
from ..models import Evaluation, Image, User
from ..quality_prediction_models import QualityPrediction
from .auto_registration import MIN_CONFIDENCE, MODEL_VERSION as YOLOE_VERSION, _infer_products
from .fruit_geometry import _evaluation

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from vision.ag055.quality_model import VERSION, predict_artifact  # noqa: E402
from vision.ag055.experimental import TASKS, describe, predict as predict_exploratory, validate_artifact  # noqa: E402
from vision.ag055.uncertainty import assess, load_policy  # noqa: E402
from vision.ag055.review import private, review_history, save_review_sample  # noqa: E402
from vision.ag055.pilot117 import load_models as load_pilot_models, predict as predict_pilot, VERSION as PILOT_VERSION  # noqa: E402
from vision.ag055.v2 import load_models as load_v2_models, predict as predict_v2  # noqa: E402

router = APIRouter(prefix='/api/evaluations', tags=['AG-055 · calidad externa experimental'])
MODEL_DIR = DATA_DIR / 'quality_models'
MAX_MODEL_BYTES = 512 * 1024
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def _load_model(product: str) -> tuple[dict | None, str | None]:
    if product not in ('mango','tomate'):
        return None, None
    configured = os.getenv('AGROSCAN_QUALITY_MODELS_PATH')
    base = Path(configured).resolve() if configured else MODEL_DIR.resolve()
    target = (base / f'ag055_quality_{product}.json').resolve()
    if not target.is_relative_to(base) or not target.is_file():
        return None, None
    try:
        raw = target.read_bytes()
    except OSError:
        raise HTTPException(503,'No se puede leer el modelo de calidad') from None
    if not raw or len(raw) > MAX_MODEL_BYTES:
        raise HTTPException(503, 'Artefacto de modelo inválido o excesivo')
    try:
        model = json.loads(raw)
    except (UnicodeDecodeError,ValueError):
        raise HTTPException(503, 'Artefacto JSON de modelo inválido') from None
    if (not isinstance(model,dict) or model.get('version') != VERSION
            or model.get('product') != product or model.get('deploymentAuthorized') is not False
            or model.get('humanReviewRequired') is not True
            or not isinstance(model.get('rubricVersion'),str)
            or not model['rubricVersion'].startswith('kent-ext-' if product == 'mango' else 'tomato-ext-')):
        raise HTTPException(503, 'Modelo incompatible o sin garantías de revisión')
    return model, hashlib.sha256(raw).hexdigest()


def _read_image(img: Image) -> bytes:
    base=DATA_DIR.resolve()
    target=(base/img.relative_path).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        raise HTTPException(409, 'La fotografía original no está disponible')
    if not 0 < img.size_bytes <= MAX_IMAGE_BYTES:
        raise HTTPException(409, 'Tamaño de evidencia inválido')
    try:
        raw=target.read_bytes()
    except OSError:
        raise HTTPException(503,'No se puede leer el almacenamiento de fotografías') from None
    if len(raw) != img.size_bytes:
        raise HTTPException(409, 'La evidencia original no coincide con su registro')
    return raw


def _assert_sources_unchanged(db, ev, sources):
    """After the first recorded analysis, an image ID cannot silently change bytes."""
    current={s['imageId']:s['sha256'] for s in sources}
    for details in db.scalars(select(QualityPrediction.details_json).where(QualityPrediction.evaluation_id==ev.id)):
        for previous in json.loads(details).get('sources',[]):
            if previous['imageId'] in current and previous['sha256']!=current[previous['imageId']]:
                raise HTTPException(409,'La fotografía cambió respecto a la evidencia original analizada')


def _snapshot_out(row: QualityPrediction) -> dict:
    return {'id':row.id,'evaluationId':f'E-{row.evaluation_id:06d}',
        'product':row.product,'status':row.status,'reason':row.reason,
        'proposedGrade':row.proposed_grade,'modelVersion':row.model_version,
        'modelSha256':row.model_sha256,'sourceFingerprint':row.source_fingerprint,
        'details':json.loads(row.details_json),
        'humanReviewRequired':True,'automaticallyFinalized':False,
        'createdAt':row.created_at.isoformat()}


@router.get('/{evaluation_id}/vision/quality/status')
def quality_status(evaluation_id: str, db: Session=Depends(get_db),
                   _user: User=Depends(require_authenticated)):
    ev=_evaluation(db,evaluation_id)
    model, digest=_load_model(ev.product)
    return {'evaluationId':evaluation_id,'product':ev.product,
        'modelAvailable':model is not None, 'modelSha256':digest,
        'stage':'experimental_pending_human_review' if model else 'blocked_no_eligible_model',
        'humanReviewRequired':True,'automaticallyFinalized':False,
        'reason':('Modelo experimental disponible; no autoriza aprobación automática'
                  if model else 'No hay modelo E0/E1/E2 elegible instalado para este producto')}


@router.get('/{evaluation_id}/vision/quality/proposals')
def list_quality(evaluation_id: str, db: Session=Depends(get_db),
                 _user: User=Depends(require_authenticated)):
    ev=_evaluation(db,evaluation_id)
    rows=db.scalars(select(QualityPrediction).where(
        QualityPrediction.evaluation_id==ev.id).order_by(QualityPrediction.id)).all()
    return [_snapshot_out(x) for x in rows]


@router.post('/{evaluation_id}/vision/quality/analyze',status_code=200)
def analyze_quality(evaluation_id: str, db: Session=Depends(get_db),
                    _user: User=Depends(require_operator)):
    ev=_evaluation(db,evaluation_id)
    if ev.status in ('cancelled','error'):
        raise HTTPException(409,'Esta evaluación no permite inferencias nuevas')
    model, model_hash=_load_model(ev.product)
    if model is None:
        return {'evaluationId':evaluation_id,'product':ev.product,
            'status':'blocked_no_eligible_model','reason':'modelo_calidad_no_disponible',
            'proposedGrade':None,'humanReviewRequired':True,'automaticallyFinalized':False}
    views=[]
    for img in sorted(ev.images,key=lambda x:x.id):
        if img.view not in {v[0].view for v in views}:
            views.append((img,_read_image(img)))
        if len(views)==2:
            break
    if len(views)<2:
        return {'evaluationId':evaluation_id,'product':ev.product,
            'status':'needs_review','reason':'se_requieren_dos_vistas_distintas',
            'proposedGrade':None,'humanReviewRequired':True,'automaticallyFinalized':False}
    sources=[{'imageId':f'I-{img.id:06d}',
              'sha256':hashlib.sha256(raw).hexdigest()} for img,raw in views]
    _assert_sources_unchanged(db,ev,sources)
    fingerprint=hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest()
    existing=db.scalar(select(QualityPrediction).where(
        QualityPrediction.evaluation_id==ev.id,
        QualityPrediction.source_fingerprint==fingerprint,
        QualityPrediction.model_sha256==model_hash))
    if existing is not None:
        return _snapshot_out(existing)
    predicted=[]
    problem=None
    for img,raw in views:
        frame=cv2.imdecode(np.frombuffer(raw,dtype=np.uint8),cv2.IMREAD_COLOR)
        if frame is None or min(frame.shape[:2]) < 128:
            problem='imagen_no_decodificable'
            break
        try:
            candidates=_infer_products(frame)
        except Exception as exc:
            raise HTTPException(503,f'YOLOE no disponible: {type(exc).__name__}') from exc
        if len(candidates)!=1:
            problem='deteccion_ambigua_o_ausente'
            break
        candidate=candidates[0]
        if (candidate['product']!=ev.product or candidate['confidence']<MIN_CONFIDENCE
                or len(candidate['polygon'])<3):
            problem='deteccion_incompatible_o_incierta'
            break
        x1,y1,x2,y2=candidate['box']
        h,w=frame.shape[:2]
        # ROI automática de YOLOE; DESPLAZAMIENTO DE DOMINIO frente a ROI manual de train.
        x=max(0,min(w-1,int(np.floor(x1))))
        y=max(0,min(h-1,int(np.floor(y1))))
        xx=max(x+1,min(w,int(np.ceil(x2))))
        yy=max(y+1,min(h,int(np.ceil(y2))))
        try:
            sample=predict_artifact(model,raw,[x,y,xx-x,yy-y])
        except (ValueError,KeyError,TypeError,ZeroDivisionError) as exc:
            problem='modelo_o_region_incompatible'
            break
        predicted.append({'imageId':f'I-{img.id:06d}',
            'imageSha256':hashlib.sha256(raw).hexdigest(),
            'bboxPx':[x,y,xx-x,yy-y],
            'detectorModel':YOLOE_VERSION,
            'suggestion':sample['proposedGrade'],
            'scoresUncalibrated':sample['scoresUncalibrated'],
            'confidenceCalibrated':False})
    grades={p['suggestion'] for p in predicted}
    agreed=not problem and len(predicted)==2 and len(grades)==1
    status='experimental_proposal' if agreed else 'needs_review'
    reason='two_views_agree_experimental_only' if agreed else (problem or 'vistas_discrepantes')
    label=predicted[0]['suggestion'] if agreed else None
    details={'sources':sources,'perView':predicted,
        'trainingTestMetrics':model.get('testMetrics'),
        'roiDistributionShiftWarning':True,
        'qualityClassifierIsNotYOLOE':True,
        'classificationScope':'condicion_externa_por_imagen',
        'rubricVersion':model.get('rubricVersion'),
        'mangoVarietyKentVerified':False if ev.product == 'mango' else None,
        'rubricIndependentlyApproved':False,
        'confidenceScoresCalibrated':False,
        'humanReviewRequired':True}
    record=QualityPrediction(evaluation_id=ev.id,product=ev.product,
        source_fingerprint=fingerprint,model_sha256=model_hash,
        model_version=VERSION,status=status,reason=reason,proposed_grade=label,
        details_json=json.dumps(details,ensure_ascii=False,allow_nan=False))
    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except IntegrityError:
        db.rollback()
        concurrent=db.scalar(select(QualityPrediction).where(
            QualityPrediction.evaluation_id==ev.id,
            QualityPrediction.source_fingerprint==fingerprint,
            QualityPrediction.model_sha256==model_hash))
        if concurrent is not None:
            return _snapshot_out(concurrent)
        raise HTTPException(409,'Conflicto registrando propuesta experimental')
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503,'No se pudo persistir la inferencia; reintentar') from None
    return _snapshot_out(record)


def _exploratory_models(product):
    configured = os.getenv('AGROSCAN_EXPLORATORY_MODELS_PATH')
    base = Path(configured).resolve() if configured else (MODEL_DIR / 'exploratory').resolve()
    found = []
    for task, (target_product, _) in TASKS.items():
        if target_product != product:
            continue
        path = base / f'ag055_exploratory_{task}.json'
        if not path.is_file():
            continue
        try:
            if not path.resolve().is_relative_to(base) or path.stat().st_size > MAX_MODEL_BYTES:
                raise ValueError('oversized')
            raw = path.read_bytes()
            artifact = json.loads(raw)
            validate_artifact(artifact, product)
            if artifact['task'] != task:
                raise ValueError('wrong task filename')
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            raise HTTPException(503, 'Modelo exploratorio incompatible') from None
        found.append((artifact, hashlib.sha256(raw).hexdigest()))
    return found


@router.get('/{evaluation_id}/vision/quality/exploratory/status')
def exploratory_status(evaluation_id: str, db: Session=Depends(get_db),
                       _user: User=Depends(require_authenticated)):
    ev = _evaluation(db, evaluation_id)
    return {'evaluationId': evaluation_id, 'experimental': True,
        'models': [{'task': m['task'], 'labels': m['labels'], 'modelVersion': m['version'],
                    'modelSha256': digest, 'operationalUseAllowed':False,
                    'diagnosticOnly':m['task']=='FG'} for m,digest in _exploratory_models(ev.product)],
        'reason': 'Etiquetas originales separadas de E0/E1/E2; confianza no calibrada'}


@router.post('/{evaluation_id}/vision/quality/exploratory/analyze')
def exploratory_analyze(evaluation_id: str, db: Session=Depends(get_db),
                        _user: User=Depends(require_operator)):
    ev = _evaluation(db, evaluation_id)
    return _analyze_experimental_models(ev,db,_exploratory_models(ev.product))


def _analyze_experimental_models(ev,db,models,pilot=False,v2=False):
    if ev.status in ('cancelled', 'error'):
        raise HTTPException(409, 'Esta evaluación no permite inferencias nuevas')
    if not models:
        raise HTTPException(409, 'No existe modelo exploratorio instalado para este producto')
    if not ev.images:
        raise HTTPException(409, 'Se requiere una fotografía persistida')
    images = [(img, _read_image(img)) for img in sorted(ev.images, key=lambda i:i.id)]
    sources = [{'imageId':f'I-{img.id:06d}', 'sha256':hashlib.sha256(raw).hexdigest()} for img,raw in images]
    _assert_sources_unchanged(db,ev,sources)
    result = []
    for model,digest in models:
        policy=None if pilot or v2 else load_policy(os.getenv('AGROSCAN_UNCERTAINTY_POLICY_PATH'),model['task'],digest,model['dataVersion'])
        context={'version':model['version'] if pilot or v2 else 'ag055-review-routing-v1','policy':policy}
        fingerprint = hashlib.sha256(json.dumps({'sources':sources,'analysisContext':context},sort_keys=True).encode()).hexdigest()
        existing = db.scalar(select(QualityPrediction).where(
            QualityPrediction.evaluation_id==ev.id,
            QualityPrediction.source_fingerprint==fingerprint,
            QualityPrediction.model_sha256==digest))
        if existing:
            result.append(_snapshot_out(existing)); continue
        try:
            predictor=predict_v2 if v2 else predict_pilot if pilot else predict_exploratory
            predictions = [{'imageId':f'I-{img.id:06d}', **predictor(model,raw)} for img,raw in images]
            if not (pilot or v2):
                for prediction in predictions:
                    prediction['uncertainty']=assess(prediction,policy)
        except (ValueError, KeyError, TypeError, OSError, IndexError):
            raise HTTPException(409, 'Imagen o modelo incompatible; evidencia insuficiente') from None
        record = QualityPrediction(evaluation_id=ev.id, product=ev.product,
            source_fingerprint=fingerprint, model_sha256=digest, model_version=model['version'],
            status='experimental_e0e1e2_v2' if v2 else 'experimental_e0e1e2_pilot' if pilot else 'exploratory_original_labels',
            reason='v2_no_external_evaluation' if v2 else 'pilot_no_independent_evaluation' if pilot else 'original_labels_not_e0_e1_e2',
            proposed_grade=None, details_json=json.dumps({'task':'PILOT117_V2' if v2 else 'PILOT117' if pilot else model['task'], 'sources':sources,
                'perView':predictions, 'experimental':True, 'labelSpace':'pilot_declared_e0e1e2_v2' if v2 else 'pilot_declared_e0e1e2' if pilot else 'original_source_labels',
                'limitations':model['limitations'], 'dataVersion':model['dataVersion'],
                'independentTestMetrics':None,'humanReviewRequired':True}, ensure_ascii=False,allow_nan=False))
        db.add(record)
        try:
            db.commit(); db.refresh(record)
        except IntegrityError:
            db.rollback()
            record = db.scalar(select(QualityPrediction).where(
                QualityPrediction.evaluation_id==ev.id,
                QualityPrediction.source_fingerprint==fingerprint,
                QualityPrediction.model_sha256==digest))
            if record is None:
                raise HTTPException(409, 'Conflicto registrando exploración') from None
        except SQLAlchemyError:
            db.rollback()
            raise HTTPException(503,'No se pudo persistir la inferencia; reintentar') from None
        result.append(_snapshot_out(record))
    return result


def _pilot_models(product):
    try:
        return load_pilot_models(os.getenv('AGROSCAN_PILOT117_MODELS_PATH'),product)
    except (OSError,ValueError,KeyError,TypeError,AttributeError):
        raise HTTPException(503,'Modelo piloto E0/E1/E2 incompatible') from None


@router.get('/{evaluation_id}/vision/quality/pilot/status')
def pilot_status(evaluation_id: str,db: Session=Depends(get_db),_user: User=Depends(require_authenticated)):
    ev=_evaluation(db,evaluation_id)
    return {'evaluationId':evaluation_id,'experimental':True,'independentTestMetrics':None,
        'models':[{'task':'PILOT117','labels':model['labels'],'modelVersion':model['version'],'modelSha256':digest}
                  for model,digest in _pilot_models(ev.product)],
        'reason':'Piloto E0/E1/E2: rendimiento independiente no evaluado; Kent no acreditado'}


@router.post('/{evaluation_id}/vision/quality/pilot/analyze')
def pilot_analyze(evaluation_id: str,db: Session=Depends(get_db),_user: User=Depends(require_operator)):
    ev=_evaluation(db,evaluation_id)
    return _analyze_experimental_models(ev,db,_pilot_models(ev.product),pilot=True)


def _v2_models(product):
    try:
        return load_v2_models(os.getenv('AGROSCAN_V2_MODELS_PATH'),product)
    except (OSError,ValueError,KeyError,TypeError,AttributeError):
        raise HTTPException(503,'Modelo V2 incompatible o no disponible') from None


@router.get('/{evaluation_id}/vision/quality/v2/status')
def v2_status(evaluation_id: str,db: Session=Depends(get_db),_user: User=Depends(require_authenticated)):
    ev=_evaluation(db,evaluation_id)
    return {'evaluationId':evaluation_id,'experimental':True,'independentTestMetrics':None,
        'models':[{'task':'PILOT117_V2','labels':model['labels'],'modelVersion':model['version'],'modelSha256':digest}
                  for model,digest in _v2_models(ev.product)],
        'reason':'V2 experimental: segmentación heurística; sin validación externa ni evidencia Kent'}


@router.post('/{evaluation_id}/vision/quality/v2/analyze')
def v2_analyze(evaluation_id: str,db: Session=Depends(get_db),_user: User=Depends(require_operator)):
    ev=_evaluation(db,evaluation_id)
    return _analyze_experimental_models(ev,db,_v2_models(ev.product),v2=True)


def _review_run():
    configured=os.getenv('AGROSCAN_REVIEW_RUN')
    if not configured:
        raise HTTPException(409,'Cola de revisión no configurada')
    try:
        root=private(Path(configured))
        if not root.is_dir():
            raise ValueError('missing directory')
        return root
    except (OSError,ValueError):
        raise HTTPException(503,'Almacenamiento de revisión no disponible') from None


def _sample(ev, img, raw):
    try:
        _,roi,method,pixels=describe(raw)
    except (ValueError,OSError):
        raise HTTPException(409,'Fotografía no decodificable para revisar la ROI') from None
    return {'id':f'eval_{ev.id}_image_{img.id}', 'source':'persisted_evaluation',
        'product':ev.product,'relative':img.relative_path,'root':str(DATA_DIR.resolve()),
        'sha256':hashlib.sha256(raw).hexdigest(),'group':f'evaluation_{ev.id}',
        'excluded':'identity_license_not_accredited', 'label':'unreviewed_original',
        'evaluationId':f'E-{ev.id:06d}','imageId':f'I-{img.id:06d}',
        'roi':roi,'roiMethod':method,'pixelSha256':pixels,'roiHumanVerified':False}


@router.get('/{evaluation_id}/vision/quality/reviews')
def list_reviews(evaluation_id: str, db: Session=Depends(get_db),
                 _user: User=Depends(require_authenticated)):
    ev=_evaluation(db,evaluation_id)
    root=_review_run()
    images=[]
    for img in ev.images:
        sample=_sample(ev,img,_read_image(img))
        try:
            history=review_history(root,sample['id'],sample['sha256'])
        except OSError:
            raise HTTPException(503,'Historial de revisión no disponible; conservar evidencia y recuperar almacenamiento') from None
        if any(e['imageSha256']!=sample['sha256'] for e in history):
            raise HTTPException(409,'La fotografía cambió respecto al historial de revisión')
        declared=history and all(e.get('annotationPurpose')=='human_label_declaration_import' for e in history)
        images.append({'imageId':sample['imageId'],'imageUrl':f'/api/images/{sample["imageId"]}',
            'imageSha256':sample['sha256'],'status':'declared_pending_metadata' if declared else 'reviewed' if history else 'pending',
            'history':history})
    return {'evaluationId':evaluation_id,'images':images,'accreditationVerified':False}


class HumanReviewInput(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    imageId: str = Field(pattern=r'^I-\d{1,9}$')
    predictionId: int = Field(gt=0)
    grade: str = Field(pattern=r'^(E0|E1|E2|no_evaluable)$')
    roi: list[int] = Field(min_length=4,max_length=4)
    roiConfirmed: bool
    humanConfirmed: bool
    rubricVersion: str = Field(min_length=3,max_length=100)
    evidence: str = Field(min_length=20,max_length=2000)
    expectedLastEventId: str | None = None


@router.post('/{evaluation_id}/vision/quality/reviews',status_code=201)
def create_human_review(evaluation_id: str, body: HumanReviewInput,
                        db: Session=Depends(get_db),user: User=Depends(require_operator)):
    ev=_evaluation(db,evaluation_id)
    if ev.status in ('cancelled','error') or not body.humanConfirmed:
        raise HTTPException(409,'Se requiere declaración humana explícita y evaluación habilitada')
    img=next((img for img in ev.images if f'I-{img.id:06d}'==body.imageId),None)
    prediction=db.get(QualityPrediction,body.predictionId)
    if img is None or prediction is None or prediction.evaluation_id!=ev.id or prediction.status not in ('exploratory_original_labels','experimental_e0e1e2_pilot','experimental_e0e1e2_v2'):
        raise HTTPException(404,'Fotografía o inferencia no pertenece a esta evaluación')
    raw=_read_image(img); sample=_sample(ev,img,raw)
    details=json.loads(prediction.details_json)
    source=next((s for s in details['sources'] if s['imageId']==body.imageId),None)
    if not source or source['sha256']!=sample['sha256']:
        raise HTTPException(409,'La fotografía no coincide con la inferencia original')
    view=next(v for v in details['perView'] if v['imageId']==body.imageId)
    try:
        return save_review_sample(_review_run(),sample,{**body.model_dump(),'reviewer':user.username},
            {'evaluationId':evaluation_id,'imageId':body.imageId,'predictionId':prediction.id,
             'modelSha256':prediction.model_sha256,'uncertainty':view.get('uncertainty'),
             'actorUserId':user.id,'actorSource':'authenticated_session',
             'roiHumanVerified':os.getenv('AGROSCAN_TEST_INSTANCE')!='1',
             'humanReviewAuthenticityVerified':False,
             'annotationPurpose':'automated_test_not_human_ground_truth' if os.getenv('AGROSCAN_TEST_INSTANCE')=='1' else 'human_declaration_unaccredited'})
    except ValueError as e:
        raise HTTPException(409 if 'history changed' in str(e) else 422,str(e)) from None
    except OSError:
        raise HTTPException(503,'No se pudo persistir la revisión; reintentar') from None
