"""Reglas de primera contratación; usa el motor c009 sin alterar empresas legacy."""
import json
from fastapi import HTTPException
from sqlalchemy import select
from ..application_models import CommercialApplication, CommercialApplicationDecision
from ..commercial_models import CommercialOnboardingOrder, CommercialPlan
from .invitations import initial_history


def same_terms(left, right):
    return {k:v for k,v in left.items() if k not in ('isActive','recommended')} == {k:v for k,v in right.items() if k not in ('isActive','recommended')}


def context(db, organization_id):
    decision = db.scalar(select(CommercialApplicationDecision).where(
        CommercialApplicationDecision.organization_id == organization_id, CommercialApplicationDecision.action == 'approve'))
    if decision is None:
        return None
    application = db.get(CommercialApplication, decision.application_id)
    accepted = next((r for r in initial_history(db, application.id) if r['accepted_at'] is not None), None)
    completion = db.scalar(select(CommercialOnboardingOrder).where(
        CommercialOnboardingOrder.organization_id == organization_id, CommercialOnboardingOrder.application_id == application.id,
        CommercialOnboardingOrder.subscription_id.is_not(None)))
    return application, accepted, completion


def output(db, organization_id):
    value = context(db, organization_id)
    if value is None:
        return None
    application, accepted, completion = value
    plan = db.get(CommercialPlan, application.requested_plan_id)
    return {'applicationId': application.id, 'organizationId': organization_id,
            'stage': 'completed' if completion else 'awaiting_demo_order' if accepted else 'awaiting_admin',
            'approvedPlan': json.loads(application.plan_snapshot_json),
            'approvedPlanAvailable': bool(plan and plan.is_active),
            'invitationId': accepted['id'] if accepted else None,
            'orderId': completion.order_id if completion else None,
            'subscriptionId': completion.subscription_id if completion else None}


def owner_outputs(db):
    companies = db.scalars(select(CommercialApplicationDecision.organization_id).where(CommercialApplicationDecision.action == 'approve'))
    return [output(db, company) for company in companies]


def validate_first(db, organization_id, plan, action, accept_updated, plan_snapshot, sub):
    value = context(db, organization_id)
    if value is None or value[2] is not None:
        return None
    application, accepted, _ = value
    if application.status != 'approved' or accepted is None:
        if sub is None:
            raise HTTPException(409, 'Incorpora al administrador mediante la invitación inicial antes de contratar.')
        return None  # Operaciones legacy conservadas; sin inferir finalización del alta.
    original = db.get(CommercialPlan, application.requested_plan_id)
    matches = plan.id == application.requested_plan_id
    if sub is None and action != 'subscribe':
        raise HTTPException(409, 'La primera contratación debe ser un alta DEMO, no cambio ni renovación.')
    if original and original.is_active:
        if not matches:
            if sub is not None:
                return None  # No asignar una contratación legacy ajena a la propuesta.
            raise HTTPException(409, 'La primera contratación debe usar el plan aprobado.')
        if not same_terms(json.loads(application.plan_snapshot_json),plan_snapshot):
            raise HTTPException(409, 'Las condiciones aprobadas cambiaron. Publica una versión vigente y confirma su selección.')
    elif not accept_updated:
        if sub is not None:
            return None
        raise HTTPException(409, 'La propuesta dejó de estar vigente. Selecciona y confirma expresamente condiciones actuales.')
    return application, accepted
