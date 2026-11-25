"""Catálogo versionado y contratación exclusivamente simulada, sin proveedor de pagos."""
import calendar
import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from ..commercial_models import CommercialOrder, CommercialPlan, CommercialSubscription, CommercialTransaction, CommercialOnboardingOrder
from ..services import commercial_onboarding as onboarding
from ..services import commercial_notifications as notifications
from ..database import get_db
from ..dependencies import require_admin
from ..models import User
from .platform import platform_context

NOTICE = 'Pago simulado — No se realizó ningún cobro'
router = APIRouter(prefix='/api/commercial', tags=['suscripciones-demo'])
owner = APIRouter(prefix='/api/platform/commercial', tags=['comercial-propietario'],
                  dependencies=[Depends(platform_context)])


def now():
    # SQLite devuelve fechas naive: toda persistencia comercial representa UTC.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def demo_enabled():
    return (os.environ.get('AGROSCAN_ENVIRONMENT') == 'demo'
            and os.environ.get('AGROSCAN_SUBSCRIPTION_SIMULATOR') == 'true')


def require_demo():
    if not demo_enabled():
        raise HTTPException(503, 'La contratación simulada no está habilitada en este entorno.')


def begin(db):
    try:
        db.connection().exec_driver_sql('BEGIN IMMEDIATE')
    except OperationalError as exc:
        db.rollback()
        raise HTTPException(503, 'Operación ocupada. Reintenta con la misma referencia.',
                            headers={'Retry-After': '2'}) from exc


class StrictBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class PlanInput(StrictBody):
    code: str = Field(pattern=r'^[a-z][a-z0-9-]{1,39}$')
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(min_length=2, max_length=500)
    amountCents: int = Field(ge=0, le=100000000)
    currency: Literal['PEN'] = 'PEN'
    period: Literal['monthly', 'annual']
    benefits: list[str] = Field(min_length=1, max_length=15)
    limits: dict[str, int] = Field(default_factory=dict, max_length=15)
    recommended: bool = False
    displayOrder: int = Field(default=0, ge=0, le=100000)
    publish: bool = True  # Compatibilidad c009; el editor nuevo guarda borradores explícitos.
    expectedVersion: int | None = Field(default=None, ge=0)
    idempotencyKey: str | None = Field(default=None, min_length=16, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    changeNote: str = Field(default='', max_length=500)

    @field_validator('name', 'description')
    @classmethod
    def trimmed(cls, value):
        if len(value.strip()) < 2:
            raise ValueError('Completa el texto del plan.')
        return value.strip()

    @field_validator('benefits')
    @classmethod
    def clean_benefits(cls, values):
        if any(not value.strip() or len(value) > 160 for value in values):
            raise ValueError('Beneficios: entre 1 y 160 caracteres.')
        return [value.strip() for value in values]

    @field_validator('limits')
    @classmethod
    def valid_limits(cls, values):
        if any(not key.strip() or len(key) > 60 or value < 0 for key, value in values.items()):
            raise ValueError('Límites no negativos con nombre válido.')
        return values


class PlanStatus(StrictBody):
    isActive: bool


class OrderInput(StrictBody):
    planId: int = Field(gt=0)
    action: Literal['subscribe', 'change', 'renew'] = 'subscribe'
    idempotencyKey: str = Field(min_length=16, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    acceptUpdatedPlan: bool = False


class ConfirmInput(StrictBody):
    scenario: Literal['approve', 'reject', 'cancel']


def plan_output(plan):
    return {'id': plan.id, 'code': plan.code, 'version': plan.version, 'name': plan.name,
            'description': plan.description, 'amountCents': plan.amount_cents,
            'currency': plan.currency, 'period': plan.period,
            'benefits': json.loads(plan.benefits_json), 'limits': json.loads(plan.limits_json),
            'isActive': plan.is_active, 'recommended': plan.recommended, 'demo': True}


def iso(value):
    return value.isoformat() + 'Z'


def owner_plan_output(plan):
    return {**plan_output(plan), 'displayOrder': plan.display_order,
            'state': 'draft' if not plan.is_published else 'active' if plan.is_active else 'inactive',
            'createdAt': iso(plan.created_at) if plan.created_at else None,
            'publishedAt': iso(plan.published_at) if plan.published_at else None,
            'createdBy': plan.created_by, 'changeNote': plan.change_note}


def subscription_output(sub):
    if sub is None:
        return None
    return {'id': sub.id, 'organizationId': sub.organization_id,
            'plan': json.loads(sub.snapshot_json),
            'status': 'expired' if sub.status == 'active' and sub.ends_at <= now() else sub.status,
            'startsAt': iso(sub.starts_at), 'endsAt': iso(sub.ends_at), 'notice': NOTICE,
            'graceEndsAt': iso(sub.ends_at + timedelta(days=7)) if sub.status == 'active' and sub.ends_at <= now() else None,
            'inGracePeriod': sub.status == 'active' and sub.ends_at <= now() < sub.ends_at + timedelta(days=7),
            'cancellationEffect': 'immediate'}


def order_output(order):
    return {'id': order.id, 'organizationId': order.organization_id, 'plan': json.loads(order.snapshot_json),
            'amountCents': order.amount_cents, 'status': order.status, 'action': order.action,
            'createdAt': iso(order.created_at), 'notice': NOTICE,
            'expiresAt': iso(order.created_at + timedelta(hours=24)),
            'isExpired': order.status == 'pending' and order.created_at + timedelta(hours=24) <= now()}


def transaction_output(tx):
    return {'id': tx.id, 'organizationId': tx.organization_id, 'orderId': tx.order_id,
            'outcome': tx.outcome, 'amountCents': tx.amount_cents,
            'createdAt': iso(tx.created_at), 'notice': NOTICE}


@router.get('/plans')
def catalog(db: Session = Depends(get_db)):
    return {'plans': [plan_output(p) for p in db.scalars(select(CommercialPlan)
            .where(CommercialPlan.is_active.is_(True), CommercialPlan.is_published.is_(True))
            .order_by(CommercialPlan.display_order, CommercialPlan.code, CommercialPlan.version.desc()))],
            'simulatorEnabled': demo_enabled(), 'notice': NOTICE}


@owner.get('/plans')
def owner_plans(db: Session = Depends(get_db)):
    return [owner_plan_output(p) for p in db.scalars(select(CommercialPlan).order_by(CommercialPlan.display_order, CommercialPlan.code, CommercialPlan.version.desc()))]


@owner.get('/plans/{plan_id}/versions')
def plan_versions(plan_id: int, db: Session = Depends(get_db)):
    plan = db.get(CommercialPlan, plan_id)
    if plan is None:
        raise HTTPException(404, 'Plan no encontrado.')
    return [owner_plan_output(p) for p in db.scalars(select(CommercialPlan).where(
        CommercialPlan.code == plan.code).order_by(CommercialPlan.version.desc()))]


@owner.post('/plans', status_code=201)
def create_plan(body: PlanInput, db: Session = Depends(get_db), user: User = Depends(platform_context)):
    begin(db)
    output = owner_plan_output if body.model_fields_set & {'publish', 'displayOrder', 'expectedVersion', 'idempotencyKey', 'changeNote'} else plan_output
    payload_hash = hashlib.sha256(json.dumps(body.model_dump(), sort_keys=True, ensure_ascii=True).encode()).hexdigest()
    if body.idempotencyKey:
        existing = db.scalar(select(CommercialPlan).where(CommercialPlan.creation_key == body.idempotencyKey))
        if existing is not None:
            if existing.creation_payload_hash != payload_hash:
                raise HTTPException(409, 'La referencia ya corresponde a otras condiciones.')
            return output(existing)
    latest = db.scalar(select(func.max(CommercialPlan.version)).where(CommercialPlan.code == body.code)) or 0
    if not body.idempotencyKey and latest:
        previous = db.scalar(select(CommercialPlan).where(CommercialPlan.code == body.code, CommercialPlan.version == latest))
        if previous.creation_payload_hash == payload_hash:
            return output(previous)
    if body.expectedVersion is not None and latest != body.expectedVersion:
        raise HTTPException(409, 'El plan tiene una versión más reciente. Actualiza el catálogo antes de editar.')
    version = latest + 1
    # Nuevas condiciones crean versión, nunca reescriben órdenes o contratos.
    if body.publish:
        for previous in db.scalars(select(CommercialPlan).where(CommercialPlan.code == body.code)):
            previous.is_active = False
    plan = CommercialPlan(code=body.code, version=version, name=body.name, description=body.description,
                          amount_cents=body.amountCents, currency=body.currency, period=body.period,
                          benefits_json=json.dumps(body.benefits), limits_json=json.dumps(body.limits),
                          recommended=body.recommended, is_active=body.publish, is_published=body.publish,
                          display_order=body.displayOrder, created_at=now(), published_at=now() if body.publish else None,
                          created_by=user.id, creation_key=body.idempotencyKey, creation_payload_hash=payload_hash, change_note=body.changeNote)
    db.add(plan)
    db.commit()
    return output(plan)


@owner.patch('/plans/{plan_id}/status')
def plan_status(plan_id: int, body: PlanStatus, db: Session = Depends(get_db)):
    begin(db)
    plan = db.get(CommercialPlan, plan_id)
    if plan is None:
        raise HTTPException(404, 'Plan no encontrado.')
    if body.isActive and db.scalar(select(CommercialPlan.id).where(
            CommercialPlan.code == plan.code, CommercialPlan.version > plan.version,
            True if not plan.is_published else CommercialPlan.is_published.is_(True))):
        raise HTTPException(409, 'Activa únicamente la versión más reciente.')
    if body.isActive:
        for previous in db.scalars(select(CommercialPlan).where(CommercialPlan.code == plan.code, CommercialPlan.id != plan.id)):
            previous.is_active = False
        if not plan.is_published:
            plan.is_published = True
            plan.published_at = now()
    plan.is_active = body.isActive
    db.commit()
    return owner_plan_output(plan)


@router.get('/subscription', dependencies=[Depends(require_admin)])
def company_overview(db: Session = Depends(get_db)):
    return {'subscription': subscription_output(db.scalar(select(CommercialSubscription))),
            'orders': [order_output(o) for o in db.scalars(select(CommercialOrder).order_by(CommercialOrder.created_at.desc()))],
            'transactions': [transaction_output(t) for t in db.scalars(select(CommercialTransaction).order_by(CommercialTransaction.id.desc()))],
            'onboarding': onboarding.output(db, db.info['organization_id']),
            'simulatorEnabled': demo_enabled(), 'notice': NOTICE}


def current_subscription(db):
    return db.scalar(select(CommercialSubscription))


@router.post('/orders', status_code=201)
def create_order(body: OrderInput, user: User = Depends(require_admin),
                 enabled=Depends(require_demo), db: Session = Depends(get_db)):
    begin(db)
    existing = db.scalar(select(CommercialOrder).where(CommercialOrder.idempotency_key == body.idempotencyKey))
    if existing:
        if existing.plan_id != body.planId or existing.action != body.action:
            raise HTTPException(409, 'Referencia reutilizada con condiciones diferentes.')
        linked = db.get(CommercialOnboardingOrder, existing.id)
        if linked and linked.accepted_updated_plan != body.acceptUpdatedPlan:
            raise HTTPException(409, 'Referencia reutilizada con otra confirmación de condiciones.')
        return order_output(existing)
    plan = db.get(CommercialPlan, body.planId)
    if plan is None or not plan.is_active:
        raise HTTPException(404, 'Plan no disponible.')
    sub = current_subscription(db)
    if body.action == 'renew' and (sub is None or sub.plan_id != plan.id):
        raise HTTPException(409, 'Renueva el plan actual o selecciona cambiar plan.')
    if body.action == 'subscribe' and sub is not None:
        raise HTTPException(409, 'Ya existe una suscripción. Selecciona cambiar o renovar.')
    first = onboarding.validate_first(db, db.info['organization_id'], plan, body.action, body.acceptUpdatedPlan, plan_output(plan), sub)
    order = CommercialOrder(id=str(uuid.uuid4()), idempotency_key=body.idempotencyKey, plan_id=plan.id,
                            created_by=user.id, snapshot_json=json.dumps(plan_output(plan)),
                            amount_cents=plan.amount_cents, action=body.action, status='pending', created_at=now())
    db.add(order)
    if first:
        db.flush([order])
        application, accepted = first
        db.add(CommercialOnboardingOrder(order_id=order.id, application_id=application.id,
            invitation_id=accepted['id'], accepted_updated_plan=body.acceptUpdatedPlan))
    db.commit()
    return order_output(order)


def add_period(start, period):
    month = start.month + (12 if period == 'annual' else 1)
    year = start.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    return start.replace(year=year, month=month, day=min(start.day, calendar.monthrange(year, month)[1]))


@router.post('/orders/{order_id}/confirm')
def confirm(order_id: str, body: ConfirmInput, user: User = Depends(require_admin),
            enabled=Depends(require_demo), db: Session = Depends(get_db)):
    begin(db)
    order = db.scalar(select(CommercialOrder).where(CommercialOrder.id == order_id))
    if order is None:
        raise HTTPException(404, 'Orden no encontrada.')
    outcome = {'approve': 'demo_approved', 'reject': 'demo_rejected', 'cancel': 'cancelled'}[body.scenario]
    if order.status != 'pending':
        if order.status != outcome:
            raise HTTPException(409, 'La orden ya tiene otro resultado definitivo.')
        return order_output(order)
    if order.created_at + timedelta(hours=24) <= now():
        raise HTTPException(409, 'La orden venció. Crea una nueva contratación.')
    plan = db.get(CommercialPlan, order.plan_id)
    if outcome == 'demo_approved':
        if not plan.is_active:
            raise HTTPException(409, 'El plan ya no está disponible. Consulta el catálogo.')
        sub = current_subscription(db)
        link = db.get(CommercialOnboardingOrder, order.id)
        if link:
            current = onboarding.context(db, order.organization_id)
            if current[2] is not None and current[2].order_id != order.id:
                raise HTTPException(409, 'El alta ya fue completada con otra orden. Prepara una nueva gestión de plan.')
            if onboarding.validate_first(db, order.organization_id, plan, order.action, link.accepted_updated_plan,
                                         json.loads(order.snapshot_json), sub) is None:
                raise HTTPException(409, 'La orden ya no corresponde al alta aprobada.')
        if order.action == 'subscribe' and sub is not None:
            raise HTTPException(409, 'La empresa ya contrató un plan. Actualiza la pantalla.')
        if order.action == 'renew' and (sub is None or sub.plan_id != order.plan_id):
            raise HTTPException(409, 'El plan cambió. Actualiza la pantalla.')
        start = now()
        end_base = max(start, sub.ends_at) if order.action == 'renew' and sub.status == 'active' else start
        end = add_period(end_base, json.loads(order.snapshot_json)['period'])
        if sub is None:
            sub = CommercialSubscription(plan_id=order.plan_id, snapshot_json=order.snapshot_json,
                                         status='active', starts_at=start, ends_at=end)
            db.add(sub)
        else:
            sub.plan_id = order.plan_id
            sub.snapshot_json = order.snapshot_json
            sub.status = 'active'
            sub.starts_at = start
            sub.ends_at = end
        if link:
            db.flush([sub])
            link.subscription_id = sub.id
    order.status = outcome
    db.add(CommercialTransaction(order_id=order.id, actor_id=user.id, outcome=outcome,
                                amount_cents=order.amount_cents if outcome == 'demo_approved' else 0,
                                created_at=now()))
    if outcome == 'demo_approved':
        notifications.organization_event(db, order.organization_id,
            {'subscribe': 'subscription_activated', 'renew': 'subscription_renewed', 'change': 'subscription_changed'}[order.action],
            order.id, json.loads(order.snapshot_json), sub.starts_at, sub.ends_at)
    db.commit()
    return order_output(order)


@router.post('/subscription/cancel')
def cancel_subscription(user: User = Depends(require_admin), enabled=Depends(require_demo),
                        db: Session = Depends(get_db)):
    begin(db)
    sub = current_subscription(db)
    if sub is None:
        raise HTTPException(404, 'No existe una suscripción.')
    if sub.status != 'cancelled':
        sub.status = 'cancelled'
        db.add(CommercialTransaction(order_id=None, actor_id=user.id, outcome='subscription_cancelled',
                                    amount_cents=0, created_at=now()))
        notifications.organization_event(db, sub.organization_id, 'subscription_cancelled',
            f'{sub.id}:{sub.starts_at.isoformat()}:{sub.ends_at.isoformat()}', json.loads(sub.snapshot_json), sub.starts_at, sub.ends_at)
    db.commit()
    return subscription_output(sub)


@owner.get('/overview')
def commercial_overview(db: Session = Depends(get_db)):
    subs = list(db.scalars(select(CommercialSubscription)))
    orders = list(db.scalars(select(CommercialOrder).order_by(CommercialOrder.created_at.desc())))
    transactions = list(db.scalars(select(CommercialTransaction).order_by(CommercialTransaction.id.desc())))
    return {'activeDemoSubscriptions': sum(s.status == 'active' and s.ends_at > now() for s in subs),
            'expiringSoon': sum(s.status == 'active' and now() < s.ends_at <= now() + timedelta(days=30) for s in subs),
            'activePlans': db.scalar(select(func.count(CommercialPlan.id)).where(CommercialPlan.is_active.is_(True))),
            'simulatedTotalCents': sum(t.amount_cents for t in transactions if t.outcome == 'demo_approved'),
            'subscriptions': [subscription_output(s) for s in subs],
            'orders': [order_output(o) for o in orders],
            'transactions': [transaction_output(t) for t in transactions], 'notice': NOTICE,
            'onboardings': onboarding.owner_outputs(db)}
