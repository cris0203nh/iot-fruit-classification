"""Administración del outbox; nunca recibe destinatarios ni cuerpos arbitrarios."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from ..database import get_db
from ..notification_models import CommercialNotification as Notice
from ..organization_models import Organization
from ..services import commercial_notifications as service
from .platform import platform_context

router = APIRouter(prefix='/api/platform/notifications', tags=['notificaciones-comerciales'], dependencies=[Depends(platform_context)])


class RetryInput(BaseModel):
    model_config = ConfigDict(extra='forbid')


def output(row):
    def utc(value):
        return value.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z') if value else None
    return {'id': row.id, 'organizationId': row.organization_id, 'event': row.event,
        'reference': row.reference, 'recipient': row.recipient, 'subject': row.subject,
        'status': row.status, 'attempts': row.attempts, 'createdAt': utc(row.created_at),
        'lastAttemptAt': utc(row.last_attempt_at), 'nextAttemptAt': utc(row.next_attempt_at),
        'smtpAcceptedAt': utc(row.smtp_accepted_at), 'errorCode': row.error_code}


@router.get('')
def listing(response: Response, organization_id: int | None = Query(None, gt=0),
            event: str | None = None, status: str | None = None, since: datetime | None = None,
            until: datetime | None = None, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
            db: Session = Depends(get_db)):
    if event and event not in service.EVENTS or status and status not in ('pending', 'processing', 'smtp_accepted', 'retry_pending', 'failed', 'omitted'):
        raise HTTPException(422, 'Filtro de notificaciones inválido.')
    filters = []
    since = since.astimezone(timezone.utc).replace(tzinfo=None) if since and since.tzinfo else since
    until = until.astimezone(timezone.utc).replace(tzinfo=None) if until and until.tzinfo else until
    if since and until and since > until:
        raise HTTPException(422, 'Intervalo de fechas inválido.')
    if organization_id is not None:
        filters.append(Notice.organization_id == organization_id)
    if event:
        filters.append(Notice.event == event)
    if status:
        filters.append(Notice.status == status)
    if since:
        filters.append(Notice.created_at >= since)
    if until:
        filters.append(Notice.created_at <= until)
    statistics = {state: count for state, count in db.execute(select(Notice.status, func.count()).where(*filters).group_by(Notice.status))}
    rows = db.scalars(select(Notice).where(*filters).order_by(Notice.created_at.desc(), Notice.id).offset(offset).limit(limit)).all()
    response.headers['Cache-Control'] = 'no-store'
    organizations = [{'id': row.id, 'name': row.name} for row in db.scalars(select(Organization).order_by(Organization.name))]
    return {'items': [output(row) for row in rows], 'total': sum(statistics.values()), 'statistics': statistics, 'organizations': organizations,
            'smtp': service.smtp_status(), 'maxAttempts': service.setting('AGROSCAN_NOTIFICATION_MAX_ATTEMPTS', 5, 1, 10)}


@router.post('/{notice_id}/retry')
def retry(notice_id: str, body: RetryInput, response: Response, db: Session = Depends(get_db)):
    row = db.get(Notice, notice_id)
    if row is None:
        raise HTTPException(404, 'Notificación no encontrada.')
    if row.status not in ('pending', 'retry_pending') or row.attempts >= service.setting('AGROSCAN_NOTIFICATION_MAX_ATTEMPTS', 5, 1, 10):
        raise HTTPException(409, 'No es elegible para reintento; no se repiten resultados inciertos o aceptados.')
    if row.next_attempt_at and row.next_attempt_at > service.now():
        raise HTTPException(429, 'Espera hasta el próximo intento autorizado.', headers={'Retry-After': str(max(1, int((row.next_attempt_at - service.now()).total_seconds())))})
    service.process_one(db, row.id)
    db.refresh(row)
    response.headers['Cache-Control'] = 'no-store'
    return output(row)
