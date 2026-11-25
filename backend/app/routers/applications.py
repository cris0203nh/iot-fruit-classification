"""Captación y decisiones del propietario; sin cuentas, invitaciones ni pagos."""
from datetime import timedelta
import hashlib
import hmac
import json
import secrets
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import Field, ValidationError, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from ..application_models import CommercialApplication, CommercialApplicationAttempt, CommercialApplicationDecision, CommercialApplicationInvitation, CommercialApplicationNotification
from ..services import application_notification
from ..services import commercial_notifications as notifications
from ..services import commercial_onboarding
from ..identity_models import OrganizationInvitation
from ..commercial_models import CommercialPlan
from ..models import User, Role
from ..organization_models import Organization, OrganizationMembership
from ..services.invitations import aware, digest, has_administrator, initial_history, now as invitation_now
from ..database import get_db
from ..security import JWT_SECRET
from ..services.google_identity import normalized_email
from .commercial import StrictBody, begin, iso, now, plan_output
from .platform import platform_context

public = APIRouter(prefix='/api/commercial/applications', tags=['solicitudes-comerciales'])
owner = APIRouter(prefix='/api/platform/commercial/applications', tags=['solicitudes-propietario'],
                  dependencies=[Depends(platform_context)])
MESSAGE = 'Solicitud recibida, pendiente de revisión'
MAX_BODY = 8192
PER_CLIENT = 5  # 10 minutos; presupuestos persistentes compartidos entre workers.
GLOBAL_PER_MINUTE = 60


class ApplicationBodyLimit:
    """Límite real de stream, incluso sin Content-Length; antes de parsear JSON."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('path', '').rstrip('/') != '/api/commercial/applications' or scope['method'] != 'POST':
            return await self.app(scope, receive, send)
        data = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            if len(data) + len(chunk) > MAX_BODY:
                return await JSONResponse({'detail': 'La solicitud supera el tamaño permitido.'}, status_code=413)(scope, receive, send)
            data.extend(chunk)
            if not message.get('more_body', False):
                break
        delivered = False
        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(data), 'more_body': False}
            return await receive()
        return await self.app(scope, replay, send)


class ApplicationInput(StrictBody):
    companyName: str = Field(min_length=2, max_length=120)
    contactName: str = Field(min_length=2, max_length=120)
    contactEmail: str = Field(min_length=3, max_length=254)
    requestedPlanId: int = Field(gt=0)
    requestedPeriod: Literal['monthly', 'annual']
    idempotencyKey: str = Field(min_length=16, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')

    @field_validator('companyName', 'contactName')
    @classmethod
    def clean_name(cls, value):
        value = ' '.join(value.split())
        if len(value) < 2 or any(ord(c) < 32 for c in value):
            raise ValueError('Nombre inválido.')
        return value

    @field_validator('contactEmail')
    @classmethod
    def email(cls, value):
        return normalized_email(value)


def sha(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def budget(db, request):
    timestamp = now()
    address = request.client.host if request.client else 'unknown'
    bucket = hmac.new(JWT_SECRET.encode(), address.encode(), hashlib.sha256).hexdigest()
    begin(db)
    # Se purgan solo contadores auxiliares; nunca solicitudes ni datos operativos.
    db.execute(delete(CommercialApplicationAttempt).where(CommercialApplicationAttempt.created_at < timestamp - timedelta(days=1)))
    recent = db.scalar(select(func.count()).select_from(CommercialApplicationAttempt).where(
        CommercialApplicationAttempt.bucket_hash == bucket,
        CommercialApplicationAttempt.created_at > timestamp - timedelta(minutes=10)))
    total = db.scalar(select(func.count()).select_from(CommercialApplicationAttempt).where(
        CommercialApplicationAttempt.created_at > timestamp - timedelta(minutes=1)))
    if recent >= PER_CLIENT or total >= GLOBAL_PER_MINUTE:
        db.rollback()
        raise HTTPException(429, 'Demasiados intentos. Inténtalo más tarde.', headers={'Retry-After': '600'})
    db.add(CommercialApplicationAttempt(bucket_hash=bucket, created_at=timestamp))
    db.commit()


def receipt(item, notification_status):
    # Siempre el recibo inicial; no revela decisiones posteriores ni datos personales.
    return {'id': item.id, 'status': 'pending', 'message': MESSAGE, 'ownerNotification': notification_status}


@public.post('', status_code=201)
async def submit(request: Request, response: Response, db: Session = Depends(get_db)):
    budget(db, request)
    try:
        body = ApplicationInput.model_validate_json(await request.body())
    except ValidationError:
        raise HTTPException(422, 'Revisa empresa, contacto, correo, plan, periodo y referencia.') from None
    payload = body.model_dump(exclude={'idempotencyKey'})
    payload['companyName'] = payload['companyName'].casefold()
    payload['contactName'] = payload['contactName'].casefold()
    payload_hash = sha(json.dumps(payload, sort_keys=True, ensure_ascii=True))
    begin(db)
    existing = db.scalar(select(CommercialApplication).where(CommercialApplication.idempotency_hash == sha(body.idempotencyKey)))
    if existing:
        if existing.payload_hash != payload_hash:
            raise HTTPException(409, 'Referencia de solicitud no disponible.')
        response.status_code = 200
        response.headers['Cache-Control'] = 'no-store'
        return receipt(existing, await application_notification.notify_once(db, existing))
    plan = db.get(CommercialPlan, body.requestedPlanId)
    if plan is None or not plan.is_active:
        raise HTTPException(404, 'Plan no disponible.')
    if plan.period != body.requestedPeriod:
        raise HTTPException(422, 'El periodo no corresponde al plan seleccionado.')
    duplicate = db.scalar(select(CommercialApplication.id).where(
        CommercialApplication.payload_hash == payload_hash, CommercialApplication.status.in_(('pending', 'under_review'))))
    if duplicate:
        raise HTTPException(409, 'No se registró otra solicitud idéntica. Conserva tu confirmación anterior.')
    item = CommercialApplication(id=str(uuid.uuid4()), company_name=body.companyName,
        contact_name=body.contactName, contact_email=body.contactEmail, requested_plan_id=plan.id,
        requested_period=body.requestedPeriod, plan_snapshot_json=json.dumps(plan_output(plan)),
        created_at=now(), status='pending', source='public_web', idempotency_hash=sha(body.idempotencyKey), payload_hash=payload_hash)
    db.add(item)
    db.add(CommercialApplicationNotification(application_id=item.id, status=application_notification.initial_status()))
    try:
        # La FK requiere persistir la solicitud antes de su registro auxiliar (sin relación ORM).
        db.flush([item])
        notifications.application_event(db, item, 'application_received')
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, 'No se pudo registrar la solicitud. Reintenta con la misma referencia.') from None
    response.headers['Cache-Control'] = 'no-store'
    return receipt(item, await application_notification.notify_once(db, item))


@owner.get('')
def list_applications(response: Response, status: Literal['pending','under_review','approved','rejected'] | None = None,
                      plan_id: int | None = Query(default=None, gt=0), limit: int = Query(default=20, ge=1, le=50),
                      offset: int = Query(default=0, ge=0, le=10000), db: Session = Depends(get_db)):
    filters = []
    if status:
        filters.append(CommercialApplication.status == status)
    if plan_id is not None:
        filters.append(CommercialApplication.requested_plan_id == plan_id)
    total = db.scalar(select(func.count()).select_from(CommercialApplication).where(*filters))
    items = db.scalars(select(CommercialApplication).where(*filters).order_by(
        CommercialApplication.created_at.desc(), CommercialApplication.id).offset(offset).limit(limit))
    response.headers['Cache-Control'] = 'no-store'
    return {'items': [application_output(db, a) for a in items], 'total': total, 'limit': limit, 'offset': offset}


def application_output(db, item):
    decisions = db.scalars(select(CommercialApplicationDecision).where(
        CommercialApplicationDecision.application_id == item.id).order_by(CommercialApplicationDecision.id)).all()
    approved = next((d for d in decisions if d.action == 'approve'), None)
    commercial = commercial_onboarding.output(db, approved.organization_id) if approved else None
    history = initial_history(db, item.id) if approved else []
    accepted = next((h for h in history if h['accepted_at'] is not None), None)
    administrator_active = False
    if accepted:
        user = db.get(User, accepted['accepted_by'])
        company = db.get(Organization, approved.organization_id)
        administrator_active = bool(user and user.is_active and company and company.is_active and db.scalar(
            select(OrganizationMembership.user_id).join(Role, Role.id == OrganizationMembership.role_id).where(
                OrganizationMembership.organization_id == approved.organization_id,
                OrganizationMembership.user_id == user.id, OrganizationMembership.is_active.is_(True), Role.name == 'administrador')))
    return {'id': item.id, 'companyName': item.company_name, 'contactName': item.contact_name,
            'contactEmail': item.contact_email, 'requestedPlanId': item.requested_plan_id, 'requestedPeriod': item.requested_period,
            'plan': json.loads(item.plan_snapshot_json), 'createdAt': iso(item.created_at), 'status': item.status, 'source': item.source,
            'organizationId': approved.organization_id if approved else None,
            'provisioningState': commercial['stage'] if commercial else 'not_provisioned',
            'commercialOrderId': commercial['orderId'] if commercial else None,
            'commercialSubscriptionId': commercial['subscriptionId'] if commercial else None,
            'administratorActive': administrator_active,
            'ownerNotification': application_notification.status(db, item.id),
            'initialInvitation': invitation_output(db, history[0]) if history else None,
            'decisions': [{'id': d.id, 'action': d.action, 'reason': d.reason, 'actorUserId': d.actor_user_id,
                           'createdAt': iso(d.created_at), 'organizationId': d.organization_id} for d in decisions]}


class DecisionInput(StrictBody):
    action: Literal['review', 'approve', 'reject']
    reason: str = Field(min_length=3, max_length=1000)
    idempotencyKey: str = Field(min_length=16, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    approvedPlanId: int | None = Field(default=None, gt=0)
    existingOrganizationId: int | None = Field(default=None, gt=0)
    identityConfirmed: bool = False

    @field_validator('reason')
    @classmethod
    def clean_reason(cls, value):
        value = value.strip()
        if len(value) < 3 or any(ord(c) < 32 and c not in '\n\r\t' for c in value):
            raise ValueError('Indica un motivo administrativo válido.')
        return value


def company_identity(name):
    return ' '.join(name.split()).casefold()


@owner.post('/{application_id}/decision')
def decide(application_id: str, body: DecisionInput, response: Response,
           user: User = Depends(platform_context), db: Session = Depends(get_db)):
    # No llama routers con commit propio ni escribe membresías/contratos/invitaciones.
    begin(db)
    item = db.get(CommercialApplication, application_id)
    if item is None:
        raise HTTPException(404, 'Solicitud no encontrada.')
    key = sha('client:' + body.idempotencyKey)
    payload_hash = sha(json.dumps(body.model_dump(exclude={'idempotencyKey'}), sort_keys=True))
    previous = db.scalar(select(CommercialApplicationDecision).where(
        CommercialApplicationDecision.application_id == item.id, CommercialApplicationDecision.idempotency_hash == key))
    if previous:
        if previous.payload_hash != payload_hash:
            raise HTTPException(409, 'La referencia ya se utilizó con otra decisión.')
        response.headers['Cache-Control'] = 'no-store'
        return application_output(db, item)
    if item.status not in ('pending', 'under_review'):
        raise HTTPException(409, 'La solicitud ya está resuelta; no se modifica la decisión.')
    if body.action != 'approve' and (body.approvedPlanId is not None or body.existingOrganizationId is not None or body.identityConfirmed):
        raise HTTPException(422, 'Solo una aprobación puede asociar empresa y plan.')
    if body.action == 'review' and item.status != 'pending':
        raise HTTPException(409, 'La solicitud ya está en revisión.')
    organization = None
    identity = None
    try:
        if body.action == 'approve':
            if not body.identityConfirmed:
                raise HTTPException(422, 'Confirma la verificación de identidad empresarial antes de aprobar.')
            plan = db.get(CommercialPlan, item.requested_plan_id)
            if plan is None or not plan.is_active or (body.approvedPlanId is not None and body.approvedPlanId != plan.id):
                raise HTTPException(409, 'El plan solicitado no está vigente. Requiere una nueva selección confirmada.')
            snapshot = json.loads(item.plan_snapshot_json)
            current = plan_output(plan)
            if any(current[k] != snapshot.get(k) for k in current if k not in ('recommended', 'isActive')):
                raise HTTPException(409, 'Las condiciones del plan cambiaron. No se modificará la propuesta original.')
            identity = company_identity(item.company_name)
            matches = [o for o in db.scalars(select(Organization)) if company_identity(o.name) == identity]
            if body.existingOrganizationId is not None:
                organization = db.get(Organization, body.existingOrganizationId)
                if organization is None:
                    raise HTTPException(404, 'Empresa seleccionada no encontrada.')
                if company_identity(organization.name) != identity or len(matches) != 1:
                    raise HTTPException(409, 'La identidad de la empresa seleccionada no coincide o es ambigua.')
            elif matches:
                raise HTTPException(409, 'Ya existe una empresa coincidente. Verifica y selecciona su vinculación explícita.')
            if db.scalar(select(CommercialApplicationDecision.id).where(
                    CommercialApplicationDecision.organization_identity == identity)) is not None:
                raise HTTPException(409, 'Esta empresa ya está asociada a otra solicitud aprobada.')
            if organization is None:
                organization = Organization(name=item.company_name)
                db.add(organization)
                db.flush()
            elif db.scalar(select(CommercialApplicationDecision.id).where(
                    CommercialApplicationDecision.organization_id == organization.id)) is not None:
                raise HTTPException(409, 'La empresa ya tiene un alta comercial asociada.')
        # Guarda también el paso de revisión al aprobar desde pending, en la misma transacción.
        if body.action == 'approve' and item.status == 'pending':
            db.add(CommercialApplicationDecision(application_id=item.id, action='review',
                reason='Revisión confirmada por el propietario antes de aprobar.', actor_user_id=user.id,
                created_at=now(), idempotency_hash=sha('automatic-review:' + body.idempotencyKey), payload_hash=payload_hash))
            db.flush()
        db.add(CommercialApplicationDecision(application_id=item.id, action=body.action, reason=body.reason,
            actor_user_id=user.id, created_at=now(), organization_id=organization.id if organization else None,
            organization_identity=identity, idempotency_hash=key, payload_hash=payload_hash))
        item.status = {'review': 'under_review', 'approve': 'approved', 'reject': 'rejected'}[body.action]
        if body.action in ('approve', 'reject'):
            notifications.application_event(db, item, 'application_approved' if body.action == 'approve' else 'application_rejected', organization.id if organization else None)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, 'No se pudo guardar la decisión. Reintenta con la misma referencia.') from None
    response.headers['Cache-Control'] = 'no-store'
    return application_output(db, item)


def invitation_output(db, row):
    binding = db.get(CommercialApplicationInvitation, row['id'])
    state = 'accepted' if row['accepted_at'] else 'revoked' if row['revoked_at'] else 'expired' if aware(row['expires_at']) <= invitation_now() else 'pending'
    return {'id': row['id'], 'email': row['email'], 'role': 'administrador', 'status': state,
            'source': 'platform_owner', 'expiresAt': aware(row['expires_at']).isoformat(),
            'createdAt': aware(row['created_at']).isoformat(),
            'acceptedAt': aware(row['accepted_at']).isoformat() if row['accepted_at'] else None,
            'acceptedBy': row['accepted_by'], 'revokedAt': aware(row['revoked_at']).isoformat() if row['revoked_at'] else None,
            'revokedBy': binding.revoked_by}


class InitialInvitationInput(StrictBody):
    action: Literal['issue', 'reissue', 'revoke'] = 'issue'
    idempotencyKey: str = Field(min_length=16, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    expiresHours: int = Field(default=48, ge=1, le=168)


@owner.post('/{application_id}/administrator-invitation')
def initial_administrator_invitation(application_id: str, body: InitialInvitationInput, response: Response,
                                    user: User = Depends(platform_context), db: Session = Depends(get_db)):
    begin(db)
    item = db.get(CommercialApplication, application_id)
    approved = db.scalar(select(CommercialApplicationDecision).where(
        CommercialApplicationDecision.application_id == application_id, CommercialApplicationDecision.action == 'approve'))
    if item is None:
        raise HTTPException(404, 'Solicitud no encontrada.')
    if item.status != 'approved' or approved is None:
        raise HTTPException(409, 'Solo una solicitud aprobada puede incorporar al primer administrador.')
    company = db.get(Organization, approved.organization_id)
    if company is None or not company.is_active:
        raise HTTPException(409, 'La empresa debe estar activa; esta operación no la reactiva.')
    key = sha(body.idempotencyKey)
    payload_hash = sha(json.dumps(body.model_dump(exclude={'idempotencyKey'}), sort_keys=True))
    previous = db.scalar(select(CommercialApplicationInvitation).where(
        CommercialApplicationInvitation.application_id == item.id, CommercialApplicationInvitation.issued_key_hash == key))
    history = initial_history(db, item.id)
    response.headers['Cache-Control'] = 'no-store'
    if previous:
        if previous.request_hash != payload_hash:
            raise HTTPException(409, 'Referencia utilizada con otra operación.')
        row = next(h for h in history if h['id'] == previous.invitation_id)
        return {'invitation': invitation_output(db, row)}  # Token irrepetible; no se recupera del hash.
    if any(h['accepted_at'] is not None for h in history):
        raise HTTPException(409, 'El primer administrador ya fue incorporado. Gestiona su membresía existente.')
    if body.action != 'revoke' and has_administrator(db, company.id):
        raise HTTPException(409, 'La empresa ya tiene un administrador registrado; no se reemplaza mediante onboarding.')
    if body.action == 'issue' and history:
        raise HTTPException(409, 'Ya existe una invitación inicial. Reemite explícitamente si necesitas otro enlace.')
    if body.action in ('reissue', 'revoke') and not history:
        raise HTTPException(409, 'No hay invitación inicial para reemplazar o revocar.')
    old_context = db.info.get('organization_id')
    token = None
    try:
        # Contexto acotado a la empresa de la aprobación validada; no membresía ni bypass global.
        db.info['organization_id'] = company.id
        if history:
            prior = db.get(OrganizationInvitation, history[0]['id'])
            binding = db.get(CommercialApplicationInvitation, prior.id)
            if prior.revoked_at is None:
                prior.revoked_at = invitation_now()
                binding.revoked_by = user.id
            binding.is_current = False
            db.flush()
        if body.action != 'revoke':
            role = db.scalar(select(Role).where(Role.name == 'administrador'))
            if role is None:
                raise HTTPException(409, 'Rol administrador no registrado.')
            token = secrets.token_urlsafe(32)
            invitation = OrganizationInvitation(organization_id=company.id, email=item.contact_email,
                role_id=role.id, created_by=user.id, token_hash=digest(token),
                expires_at=invitation_now() + timedelta(hours=body.expiresHours))
            db.add(invitation)
            db.flush()
            db.add(CommercialApplicationInvitation(invitation_id=invitation.id, application_id=item.id,
                organization_id=company.id, issued_key_hash=key, request_hash=payload_hash, is_current=True))
            notifications.enqueue(db, 'administrator_invited', str(invitation.id), item.contact_email,
                organization_id=company.id, name=item.contact_name, plan=json.loads(item.plan_snapshot_json))
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, 'No se pudo guardar la invitación. Reintenta con la misma referencia.') from None
    finally:
        db.info['organization_id'] = old_context
    latest = initial_history(db, item.id)[0]
    result = {'invitation': invitation_output(db, latest)}
    if token:
        response.status_code = 201
        result['token'] = token
    return result
