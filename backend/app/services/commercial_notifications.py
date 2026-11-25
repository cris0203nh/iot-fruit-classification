"""Intentos durables y entrega fuera de la transacción comercial; SMTP no es exactly-once."""
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr
from email.headerregistry import Address
from email.errors import HeaderParseError
from html import escape
from urllib.parse import urlsplit
import json
import os
import smtplib
import uuid

from sqlalchemy import select, update, or_
from sqlalchemy.exc import SQLAlchemyError
from ..notification_models import CommercialNotification as Notice
from ..application_models import CommercialApplicationNotification
from ..commercial_models import CommercialSubscription
from ..identity_models import OrganizationInvitation, GoogleIdentity
from ..models import User, Role
from ..organization_models import Organization, OrganizationMembership
from . import application_notification as transport
from .google_identity import normalized_email

EVENTS = {
    'application_received': 'Nueva solicitud comercial pendiente',
    'application_approved': 'Solicitud aprobada: incorporación pendiente',
    'application_rejected': 'Resultado de tu solicitud comercial',
    'administrator_invited': 'Invitación empresarial preparada',
    'administrator_activated': 'Acceso empresarial incorporado',
    'subscription_activated': 'Suscripción DEMO activada',
    'subscription_renewed': 'Renovación DEMO confirmada',
    'subscription_changed': 'Cambio de plan DEMO confirmado',
    'subscription_expiring': 'Próximo vencimiento de suscripción DEMO',
    'subscription_expired': 'Suscripción DEMO vencida',
    'subscription_cancelled': 'Cancelación DEMO confirmada',
}
NEXT = {
    'application_received': 'Revisa la solicitud en la bandeja privada. No está aprobada.',
    'application_approved': 'La aprobación no activa una suscripción. Recibirás el enlace seguro del primer administrador por el canal acordado.',
    'application_rejected': 'La solicitud fue rechazada. Puedes contactar con AgroScan para aclaraciones.',
    'administrator_invited': 'El propietario ha preparado tu invitación. Solicita el enlace seguro por el canal acordado; este aviso no contiene el token y no concede acceso por sí solo.',
    'administrator_activated': 'Tu acceso empresarial fue incorporado. Inicia sesión para consultar la situación comercial de tu empresa. La membresía de administrador no confirma un pago ni activa por sí sola una suscripción.',
    'subscription_activated': 'Consulta tu plan y vigencia en el panel empresarial.',
    'subscription_renewed': 'Consulta la nueva vigencia registrada en tu panel.',
    'subscription_changed': 'El cambio confirmado conserva su propia versión contractual.',
    'subscription_expiring': 'Consulta las opciones de renovación. No habrá cobros automáticos.',
    'subscription_expired': 'La gracia informativa es de siete días. Este aviso no modifica el contrato ni elimina datos.',
    'subscription_cancelled': 'La cancelación es inmediata según las reglas DEMO; los históricos se conservan.',
}
DEMO = 'Pago simulado — No se realizó ningún cobro'


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def setting(name, default, minimum, maximum):
    value = int(os.getenv(name, str(default)))
    if not minimum <= value <= maximum:
        raise ValueError('Invalid notification configuration')
    return value


def valid_email(value):
    try:
        email = normalized_email(value or '')
        if any(char in email for char in ',;<>'):
            return None
        Address(addr_spec=email)
        return email
    except (ValueError, TypeError, HeaderParseError):
        return None


def enqueue(db, event, reference, recipient, *, organization_id=None, user_id=None,
            name='', plan=None, starts_at=None, ends_at=None, suffix='contact', company='', contact_email=''):
    if event not in EVENTS:
        raise ValueError('Unknown commercial event')
    key = f'{event}:{reference}:{suffix}'
    if db.scalar(select(Notice.id).where(Notice.event_key == key)) or any(
            isinstance(row, Notice) and row.event_key == key for row in db.new):
        return False
    email = valid_email(recipient)
    # Solo valores comerciales seleccionados del snapshot, nunca tokens o credenciales.
    terms = {k: plan[k] for k in ('name', 'version', 'amountCents', 'currency', 'period', 'benefits', 'limits') if k in (plan or {})}
    payload = {'name': name, 'company': company, 'contactEmail': contact_email,
               'plan': terms, 'startsAt': starts_at.isoformat() if starts_at else None,
               'endsAt': ends_at.isoformat() if ends_at else None}
    db.add(Notice(id=str(uuid.uuid4()), event_key=key, organization_id=organization_id,
        recipient_user_id=user_id, event=event, reference=reference, recipient=email,
        subject='AgroScan — ' + EVENTS[event], payload_json=json.dumps(payload),
        status='pending' if email else 'omitted', attempts=0, created_at=now(),
        error_code=None if email else 'recipient_unavailable'))
    return True


def application_event(db, item, event, organization_id=None):
    owner = event == 'application_received'
    enqueue(db, event, item.id, os.getenv('AGROSCAN_COMMERCIAL_OWNER_EMAIL', '') if owner else item.contact_email,
        organization_id=organization_id, name=item.contact_name, company=item.company_name,
        contact_email=item.contact_email if owner else '', plan=json.loads(item.plan_snapshot_json),
        suffix='owner' if owner else 'contact')


def administrator_recipients(db, organization_id):
    users = db.scalars(select(User).join(OrganizationMembership, OrganizationMembership.user_id == User.id)
        .join(Role, Role.id == OrganizationMembership.role_id)
        .join(Organization, Organization.id == OrganizationMembership.organization_id)
        .where(Organization.id == organization_id, Organization.is_active.is_(True),
               User.is_active.is_(True), OrganizationMembership.is_active.is_(True), Role.name == 'administrador')).all()
    result = []
    for user in users:
        invitation = db.scalar(select(OrganizationInvitation).where(
            OrganizationInvitation.organization_id == organization_id,
            OrganizationInvitation.accepted_by == user.id, OrganizationInvitation.role_id ==
            select(Role.id).where(Role.name == 'administrador').scalar_subquery(),
            OrganizationInvitation.accepted_at.is_not(None)).order_by(OrganizationInvitation.id.desc()))
        identity = db.scalar(select(GoogleIdentity).where(GoogleIdentity.user_id == user.id))
        result.append((user.id, user.full_name, invitation.email if invitation else identity.email if identity else None))
    return result or [(None, '', None)]


def organization_event(db, org, event, reference, plan, starts_at, ends_at):
    queued = 0
    for user_id, name, email in administrator_recipients(db, org):
        queued += enqueue(db, event, reference, email, organization_id=org, user_id=user_id,
            name=name, plan=plan, starts_at=starts_at, ends_at=ends_at, suffix=str(user_id or 'no-recipient'))
    return queued


def smtp_status():
    if not transport.enabled():
        return {'enabled': False, 'configured': False, 'reason': 'smtp_disabled'}
    try:
        transport.configuration('validation@example.test')
        setting('AGROSCAN_SMTP_TIMEOUT_SECONDS', 5, 1, 30)
    except (ValueError, TypeError):
        return {'enabled': True, 'configured': False, 'reason': 'configuration_error'}
    return {'enabled': True, 'configured': True, 'reason': None}


def message_for(row, config):
    data = json.loads(row.payload_json)
    lines = [f'Hola {data["name"] or "equipo"},', EVENTS[row.event], f'Referencia: {row.reference}']
    if data['company']:
        lines.append('Empresa: ' + data['company'])
    if data['contactEmail']:
        lines.append('Correo de contacto: ' + data['contactEmail'])
    plan = data['plan']
    if plan:
        lines.extend([f'Plan: {plan["name"]} (v{plan["version"]})',
            f'Periodo: {plan["period"]}', f'Importe referencial DEMO: {plan["amountCents"] // 100}.{plan["amountCents"] % 100:02d} PEN'])
        lines.extend(str(x) for x in plan.get('benefits', []))
        lines.extend(f'{k}: {v} (referencial)' for k, v in plan.get('limits', {}).items())
    for label, field in [('Inicio', 'startsAt'), ('Vencimiento', 'endsAt')]:
        if data[field]:
            lines.append(f'{label}: {data[field]} UTC')
    lines.extend([NEXT[row.event], DEMO, 'Aceptación SMTP no acredita recepción en el buzón.'])
    base = os.getenv('AGROSCAN_PUBLIC_URL', '').rstrip('/')
    parsed = urlsplit(base)
    if (parsed.scheme == 'https' or parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1')) and parsed.hostname and not (parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path):
        lines.append(base + ('/plataforma/solicitudes' if row.event == 'application_received' else '/acceso'))
    message = EmailMessage()
    display = os.getenv('AGROSCAN_SMTP_FROM_NAME', 'AgroScan').strip()
    if len(display) > 100 or '\r' in display or '\n' in display:
        raise ValueError('Invalid sender name')
    message['From'] = formataddr((display, config.sender))
    message['To'], message['Subject'] = config.recipient, row.subject
    message['Message-ID'] = f'<notification.{row.id}@{config.sender.rsplit("@", 1)[1]}>'
    message.set_content('\n\n'.join(lines))
    message.add_alternative('<html lang="es"><body style="background:#f5f2e9;color:#183b2a;font:16px Arial;padding:28px"><h1>AgroScan</h1>' +
        ''.join('<p>' + escape(line) + '</p>' for line in lines) + '</body></html>', subtype='html')
    return message


def _legacy(db, row, status):
    if row.event == 'application_received':
        db.execute(update(CommercialApplicationNotification).where(
            CommercialApplicationNotification.application_id == row.reference).values(status=status,
            attempted_at=row.last_attempt_at, completed_at=now() if status != 'sending' else None,
            error_code=row.error_code))


def process_one(db, notice_id):
    row = db.get(Notice, notice_id, populate_existing=True)
    maximum = setting('AGROSCAN_NOTIFICATION_MAX_ATTEMPTS', 5, 1, 10)
    delay = setting('AGROSCAN_NOTIFICATION_RETRY_SECONDS', 60, 1, 86400)
    if row is None or row.status not in ('pending', 'retry_pending') or row.attempts >= maximum or row.next_attempt_at and row.next_attempt_at > now():
        return False
    if row.event == 'administrator_invited':
        invitation = db.get(OrganizationInvitation, int(row.reference))
        if (invitation is None or invitation.organization_id != row.organization_id
                or invitation.revoked_at or invitation.accepted_at
                or invitation.expires_at.replace(tzinfo=None) <= now()):
            row.status, row.error_code = 'omitted', 'invitation_no_longer_available'
            db.commit()
            return False
    if row.recipient_user_id is not None and not any(uid == row.recipient_user_id and valid_email(email) == row.recipient for uid, _, email in administrator_recipients(db, row.organization_id)):
        row.status, row.error_code = 'omitted', 'recipient_no_longer_authorized'
        db.commit()
        return False
    configuration = smtp_status()
    if not configuration['configured']:
        row.error_code = configuration['reason']; row.next_attempt_at = now() + timedelta(seconds=delay)
        _legacy(db, row, 'disabled' if not configuration['enabled'] else 'failed')
        db.commit()
        return False
    claim = str(uuid.uuid4())
    changed = db.execute(update(Notice).where(Notice.id == notice_id, Notice.status.in_(('pending', 'retry_pending')),
        Notice.attempts < maximum, or_(Notice.next_attempt_at.is_(None), Notice.next_attempt_at <= now())).values(
        status='processing', attempts=Notice.attempts + 1, last_attempt_at=now(), claim_id=claim, error_code=None))
    if changed.rowcount != 1:
        db.rollback()
        return False
    db.refresh(row); _legacy(db, row, 'sending'); db.commit()
    # Copia separada: terminar también la transacción de lectura antes de SMTP.
    db.refresh(row)
    payload = {k: getattr(row, k) for k in ('id', 'recipient', 'subject', 'payload_json', 'event', 'reference', 'attempts')}
    db.rollback()
    from types import SimpleNamespace
    detached = SimpleNamespace(**payload)
    result, error = 'smtp_accepted', None
    try:
        config = transport.configuration(detached.recipient)
        transport.send(config, message_for(detached, config))
    except smtplib.SMTPAuthenticationError:
        result, error = 'retry_pending', 'smtp_authentication_error'
    except (TimeoutError, ConnectionResetError, smtplib.SMTPServerDisconnected):
        # Puede haber ocurrido después de DATA: nunca reenvío automático ambiguo.
        result, error = 'failed', 'delivery_uncertain'
    except (ConnectionRefusedError, smtplib.SMTPConnectError, smtplib.SMTPException):
        result, error = 'retry_pending', 'smtp_transport_error'
    except OSError:
        result, error = 'failed', 'delivery_uncertain'
    except (ValueError, TypeError):
        result, error = 'retry_pending', 'configuration_error'
    except Exception:
        result, error = 'failed', 'delivery_uncertain'
    if result == 'retry_pending' and detached.attempts >= maximum:
        result = 'failed'
    try:
        row = db.get(Notice, notice_id, populate_existing=True)
        if row.claim_id != claim or row.status != 'processing':
            return False
        row.status, row.error_code = result, error
        row.next_attempt_at = now() + timedelta(seconds=min(delay * 2 ** (row.attempts - 1), 86400)) if result == 'retry_pending' else None
        row.smtp_accepted_at = now() if result == 'smtp_accepted' else None
        _legacy(db, row, 'sent' if result == 'smtp_accepted' else 'failed')
        db.commit()
    except SQLAlchemyError:
        db.rollback()  # Claimed processing persists: do not blindly resend.
    return True


def process_pending(db, limit=50):
    # Una reclamación abandonada es incierta, no un mensaje listo para repetir.
    db.execute(update(Notice).where(Notice.status == 'processing', Notice.last_attempt_at < now() - timedelta(minutes=10))
        .values(status='failed', error_code='delivery_uncertain'))
    db.commit()
    ids = list(db.scalars(select(Notice.id).where(Notice.status.in_(('pending', 'retry_pending')),
        or_(Notice.next_attempt_at.is_(None), Notice.next_attempt_at <= now())).order_by(Notice.created_at).limit(limit)))
    return sum(process_one(db, notice_id) for notice_id in ids)


def enqueue_expirations(db, limit=100):
    db.connection().exec_driver_sql('BEGIN IMMEDIATE')
    days = setting('AGROSCAN_NOTIFICATION_EXPIRY_DAYS', 7, 1, 90)
    lookback = setting('AGROSCAN_NOTIFICATION_EXPIRED_LOOKBACK_DAYS', 30, 1, 365)
    current = now()
    subscriptions = db.scalars(select(CommercialSubscription).where(CommercialSubscription.status == 'active',
        CommercialSubscription.ends_at <= current + timedelta(days=days),
        CommercialSubscription.ends_at >= current - timedelta(days=lookback)).order_by(CommercialSubscription.ends_at, CommercialSubscription.id)).yield_per(100)
    queued = 0
    for sub in subscriptions:
        event = 'subscription_expired' if sub.ends_at <= current else 'subscription_expiring'
        reference = f'{sub.id}:{sub.ends_at.isoformat()}:{days if event == "subscription_expiring" else 0}'
        queued += organization_event(db, sub.organization_id, event, reference, json.loads(sub.snapshot_json), sub.starts_at, sub.ends_at)
        if queued >= limit:
            break
    db.commit()
    return queued
