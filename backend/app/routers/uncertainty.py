"""AG-037: immutable automatic detection evidence and reviewer resolution.

YOLOE detects mango/tomato; it NEVER predicts E0/E1/E2. Results are attached to
already saved photographs and NEVER overwrite the image or an initial category.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import DATA_DIR, get_db
from ..dependencies import require_authenticated, require_reviewer
from ..models import Evaluation, Image, Review, User
from ..review_completion import pending_ag037_images, reconcile_review_status
from ..uncertainty import CAPTURE_THRESHOLD, RULE_VERSION, GateResult, classify_detection
from ..vision_assessment_models import VisionAssessment
from .images import _VISION_INFERENCE_LOCK, get_vision_model

router = APIRouter(prefix='/api/evaluations', tags=['incertidumbre'])
IMAGE_ID_PATTERN = re.compile(r'I-(\d{1,9})\Z')
EVAL_ID_PATTERN = re.compile(r'E-(\d{1,9})\Z')
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MODEL_ID = 'yoloe-26n-seg-local'
INFERENCE_SIZE = 512
INFERENCE_CONF = 0.25


class ReviewGateRequest(BaseModel):
    imageId: str
    forceReview: bool = False
    note: str = ''

    @field_validator('imageId')
    @classmethod
    def valid_image(cls, value: str) -> str:
        if not IMAGE_ID_PATTERN.fullmatch(value):
            raise ValueError('imageId inválido')
        return value

    @field_validator('note')
    @classmethod
    def valid_note(cls, value: str) -> str:
        result = value.strip()
        if len(result) > 300:
            raise ValueError('Motivo demasiado extenso')
        return result


class ResolutionRequest(BaseModel):
    outcome: str
    reason: str

    @field_validator('outcome')
    @classmethod
    def valid_outcome(cls, value: str) -> str:
        if value not in ('E0','E1','E2','no_evaluable'):
            raise ValueError('Solo E0/E1/E2 o no_evaluable')
        return value

    @field_validator('reason')
    @classmethod
    def valid_reason(cls, value: str) -> str:
        result = value.strip()
        if not 10 <= len(result) <= 500:
            raise ValueError('Justificación entre 10 y 500 caracteres')
        return result


def _eval(db: Session, evaluation_id: str) -> Evaluation:
    match = EVAL_ID_PATTERN.fullmatch(evaluation_id)
    ev = db.get(Evaluation, int(match.group(1))) if match else None
    if not ev:
        raise HTTPException(404,'Evaluación inexistente')
    return ev


def _source_bytes(image: Image) -> tuple[bytes,str]:
    root = DATA_DIR.resolve(strict=True)
    rel = image.relative_path
    if not rel or '\\' in rel or ':' in rel:
        raise HTTPException(409,'Referencia de fotografía inválida')
    relative = PurePosixPath(rel)
    if relative.is_absolute() or '..' in relative.parts:
        raise HTTPException(409,'Referencia de fotografía insegura')
    path = root.joinpath(*relative.parts)
    if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
        raise HTTPException(409,'Fotografía original no disponible')
    if path.stat().st_size > MAX_IMAGE_BYTES:
        raise HTTPException(409,'Fotografía fuera de límites')
    raw = path.read_bytes()
    if not raw or len(raw) != image.size_bytes:
        raise HTTPException(409,'Fotografía original ausente/inconsistente')
    return raw, hashlib.sha256(raw).hexdigest()


def _infer(raw: bytes, product: str) -> tuple[GateResult,list[dict]]:
    frame = cv2.imdecode(np.frombuffer(raw,dtype=np.uint8),cv2.IMREAD_COLOR)
    if frame is None:
        return GateResult(True,'imagen_no_evaluable',None,0), []
    with _VISION_INFERENCE_LOCK:
        prediction = get_vision_model().predict(source=frame,imgsz=INFERENCE_SIZE,
             conf=INFERENCE_CONF,iou=.50,max_det=10,device='cpu',verbose=False)[0]
    detections=[]
    if prediction.boxes is not None:
        polygons = prediction.masks.xy if prediction.masks is not None else []
        for index,box in enumerate(prediction.boxes):
            classid=int(box.cls[0].item())
            label=(prediction.names.get(classid,'') if isinstance(prediction.names,dict)
                   else prediction.names[classid])
            detections.append({'label':str(label)[:80],
                               'confidence':round(float(box.conf[0].item()),7),
                               'box':[round(float(x),2) for x in box.xyxy[0].tolist()],
                               'mask':bool(index<len(polygons) and len(polygons[index])>=3)})
    return classify_detection(product,detections), detections


def _assessment_out(row: VisionAssessment) -> dict:
    return {'id':row.id,'evaluationId':f'E-{row.evaluation_id:06d}',
            'imageId':f'I-{row.image_id:06d}', 'imageSha256':row.image_sha256,
            'modelVersion':row.model_version, 'rulesVersion':row.rules_version,
            'threshold':row.acceptance_threshold, 'inferenceSize':row.inference_size,
            'outcome':row.outcome, 'reason':row.reason,
            'confidence':row.confidence, 'candidateCount':row.candidate_count,
            'detections':json.loads(row.detections_json),
            'createdAt':row.created_at.isoformat()}


def _flag_pending(db: Session, ev: Evaluation, img: Image, sha: str, reason: str,
                  user: User, note: str) -> bool:
    # One unresolved event per image+source hash. Human notes never replace prior events.
    marker=f'AG037|image=I-{img.id:06d}|sha256={sha}|'
    last_events=list(ev.reviews)
    if ev.status=='pending_review' and any(
        r.type=='uncertainty' and r.reason.startswith(marker) for r in last_events):
        return True
    why=note.replace('|','/').replace('\n',' ').strip()
    event=Review(evaluation_id=ev.id,type='uncertainty',actor_id=user.username,
        reason=(f'{marker}cause={reason}|note={why}')[:500],
        previous_value=ev.status,updated_value='pending_review')
    db.add(event)
    ev.status='pending_review'
    return False


@router.post('/{evaluation_id}/vision/review-gate')
def review_gate(evaluation_id: str,payload: ReviewGateRequest,
                db:Session=Depends(get_db),user:User=Depends(require_authenticated)):
    ev=_eval(db,evaluation_id)
    if ev.status not in ('processing','completed','pending_review'):
        raise HTTPException(409,'Evaluación anulada o en error')
    match=IMAGE_ID_PATTERN.fullmatch(payload.imageId)
    img=db.get(Image,int(match.group(1))) if match else None
    if img is None or img.evaluation_id!=ev.id:
        raise HTTPException(404,'Fotografía no asociada')
    if payload.forceReview:
        if not any(role.name in ('administrador','revisor') for role in user.roles):
            raise HTTPException(403,'Se requiere perfil revisor')
        if len(payload.note)<10:
            raise HTTPException(422,'Indique por qué necesita revisión')
    elif ev.status=='completed':
        raise HTTPException(409,'No repetir inferencia automática en una evaluación cerrada')
    raw,sha=_source_bytes(img)
    previous=db.scalar(select(VisionAssessment).where(
        VisionAssessment.image_id==img.id,
        VisionAssessment.image_sha256==sha,
        VisionAssessment.rules_version==RULE_VERSION,
        VisionAssessment.model_version==MODEL_ID,
    ).order_by(VisionAssessment.id.desc()))
    if payload.forceReview:
        result=GateResult(True,'solicitud_manual',None,0)
        existing=_flag_pending(db,ev,img,sha,result.reason,user,payload.note)
        db.commit()
    else:
        existing=previous is not None
        if previous is not None:
            result=GateResult(previous.outcome=='pending_review',previous.reason,
                              previous.confidence,previous.candidate_count)
        else:
            try:
                result,detections=_infer(raw,ev.product)
            except Exception:
                result,detections=GateResult(True,'detector_no_disponible',None,0),[]
            # Guardar salida original aun cuando sea apta. No alterar los bytes.
            _,after_sha=_source_bytes(img)
            if after_sha!=sha:
                raise HTTPException(409,'Imagen alterada durante inferencia')
            previous=VisionAssessment(evaluation_id=ev.id,image_id=img.id,image_sha256=sha,
                model_version=MODEL_ID,rules_version=RULE_VERSION,inference_size=INFERENCE_SIZE,
                inference_confidence=INFERENCE_CONF,acceptance_threshold=CAPTURE_THRESHOLD,
                outcome='pending_review' if result.pending else 'ready_to_capture',
                reason=result.reason,confidence=result.confidence,
                candidate_count=result.candidate_count,
                detections_json=json.dumps(detections,ensure_ascii=False,allow_nan=False))
            db.add(previous)
        if result.pending:
            _flag_pending(db,ev,img,sha,result.reason,user,'')
        db.commit()
    return {'evaluationId':evaluation_id,'imageId':payload.imageId,
            'status':ev.status,'decision':'pending_review' if result.pending else 'ready_to_capture',
            'reason':result.reason,'imageSha256':sha,'threshold':CAPTURE_THRESHOLD,
            'confidence':result.confidence,'candidateCount':result.candidate_count,
            'assessmentId':previous.id if previous else None,
            'eventAlreadyRecorded':existing,'originalPreserved':True,
            'visualCategoryChanged':False,'classificationE0E1E2Produced':False}


@router.get('/{evaluation_id}/vision/assessments')
def assessments(evaluation_id:str,db:Session=Depends(get_db),
                user:User=Depends(require_authenticated)):
    ev=_eval(db,evaluation_id)
    records=db.scalars(select(VisionAssessment).where(
        VisionAssessment.evaluation_id==ev.id).order_by(VisionAssessment.id)).all()
    return [_assessment_out(row) for row in records]


@router.post('/{evaluation_id}/vision/resolve')
def resolve(evaluation_id:str,payload:ResolutionRequest,
                db:Session=Depends(get_db),user:User=Depends(require_reviewer)):
    ev=_eval(db,evaluation_id)
    if ev.status!='pending_review':
        raise HTTPException(409,'Solo se resuelven evaluaciones pendientes')
    if not any(r.type=='uncertainty' for r in ev.reviews):
        raise HTTPException(409,'No existe incertidumbre documentada')
    # The legacy route has no imageId. It cannot resolve two distinct photos.
    if len(pending_ag037_images(db, ev, DATA_DIR)) > 1:
        raise HTTPException(409, 'Hay varias fotos pendientes; use AG-038 por imagen')
    # Los dictámenes humanos se guardan como evento; la categoría inicial NO cambia.
    original=ev.visual_category
    last=next((r.updated_value for r in reversed(ev.reviews) if r.type=='review'),original)
    db.add(Review(evaluation_id=ev.id,type='review',actor_id=user.username,
                  reason=f'AG037|revision_humana|{payload.reason}',
                  previous_value=last,updated_value=payload.outcome))
    db.flush()
    if reconcile_review_status(db, ev, DATA_DIR):
        db.rollback()
        raise HTTPException(409, 'Persisten incidencias por fotografía; use AG-038')
    ev.review_note=payload.reason
    db.commit()
    return {'evaluationId':evaluation_id,'status':ev.status,
            'reviewOutcome':payload.outcome,'originalVisualCategory':original,
            'originalPreserved':True,'actorId':user.username}
