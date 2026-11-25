"""Transporte SMTP reutilizable y compatibilidad con avisos c013 anteriores al outbox."""
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.headerregistry import Address
from email.errors import HeaderParseError
import json
import logging
import os
import smtplib
import ssl

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from ..application_models import CommercialApplicationNotification
from .google_identity import normalized_email

logger = logging.getLogger(__name__)


def enabled():
    return os.getenv('AGROSCAN_SMTP_ENABLED') == 'true'


def initial_status():
    return 'pending' if enabled() else 'disabled'


def status(db, application_id):
    return db.scalar(select(CommercialApplicationNotification.status).where(
        CommercialApplicationNotification.application_id == application_id)) or 'not_requested'


@dataclass(frozen=True)
class Configuration:
    host: str
    port: int
    security: str
    sender: str
    recipient: str
    username: str
    password: str


def configuration(recipient=None):
    if not enabled():
        raise ValueError('SMTP not enabled')
    host = os.getenv('AGROSCAN_SMTP_HOST', '').strip()
    security = os.getenv('AGROSCAN_SMTP_SECURITY', 'starttls')
    port = int(os.getenv('AGROSCAN_SMTP_PORT', '465' if security == 'ssl' else '587'))
    username, password = os.getenv('AGROSCAN_SMTP_USERNAME', ''), os.getenv('AGROSCAN_SMTP_PASSWORD', '')
    if (not host or len(host) > 253 or any(c.isspace() for c in host) or not 1 <= port <= 65535
            or security not in ('starttls','ssl','plain') or bool(username) != bool(password)
            or (security == 'plain' and host not in ('localhost','127.0.0.1','::1'))):
        raise ValueError('Invalid SMTP configuration')
    sender = normalized_email(os.getenv('AGROSCAN_SMTP_FROM', ''))
    destination = normalized_email(recipient if recipient is not None else os.getenv('AGROSCAN_COMMERCIAL_OWNER_EMAIL', ''))
    try:
        for email in (sender, destination):
            if any(char in email for char in ',;<>'):
                raise ValueError('Invalid SMTP address')
            Address(addr_spec=email)
    except HeaderParseError:
        raise ValueError('Invalid SMTP address') from None
    display = os.getenv('AGROSCAN_SMTP_FROM_NAME', 'AgroScan').strip()
    if len(display) > 100 or '\r' in display or '\n' in display:
        raise ValueError('Invalid sender name')
    return Configuration(host, port, security, sender, destination, username, password)


def message_for(item, config):
    plan = json.loads(item.plan_snapshot_json)
    whole, cents = divmod(plan['amountCents'], 100)
    message = EmailMessage()
    message['From'], message['To'] = config.sender, config.recipient
    message['Subject'] = 'AgroScan — Nueva solicitud comercial pendiente'
    message['Message-ID'] = f'<application.{item.id}@{config.sender.rsplit("@",1)[1]}>'
    message.set_content(f'Solicitud recibida, pendiente de revisión.\n\nReferencia: {item.id}\n'
        f'Empresa: {item.company_name}\nContacto: {item.contact_name}\nCorreo: {item.contact_email}\n'
        f'Plan: {plan["name"]} (v{plan["version"]})\nPeriodo: {item.requested_period}\n'
        f'Importe referencial DEMO: {whole}.{cents:02d} PEN\n\n'
        'Consulta la bandeja privada de solicitudes de AgroScan. No se aprobó el alta ni se realizó ningún cobro.')
    return message


def send(config, message):
    context = ssl.create_default_context()
    timeout = int(os.getenv('AGROSCAN_SMTP_TIMEOUT_SECONDS', '5'))
    if not 1 <= timeout <= 30:
        raise ValueError('Invalid SMTP timeout')
    transport = smtplib.SMTP_SSL(config.host, config.port, timeout=timeout, context=context) if config.security == 'ssl' else smtplib.SMTP(config.host, config.port, timeout=timeout)
    with transport as smtp:
        if config.security == 'starttls':
            smtp.ehlo(); smtp.starttls(context=context); smtp.ehlo()
        if config.username:
            smtp.login(config.username, config.password)
        if smtp.send_message(message):
            raise smtplib.SMTPException('Recipient not accepted')


async def notify_once(db, item):
    # Nuevas solicitudes usan el outbox; la tabla c013 conserva su proyección API.
    from . import commercial_notifications as queue
    from ..notification_models import CommercialNotification
    queued = db.scalar(select(CommercialNotification.id).where(
        CommercialNotification.event_key == 'application_received:' + item.id + ':owner'))
    if queued:
        current = status(db, item.id)
        if current != 'pending':
            return current
        try:
            await run_in_threadpool(queue.process_one, db, queued)
        except SQLAlchemyError:
            db.rollback()
            logger.warning('commercial_notification_processing_unavailable')
            return 'sending'
        return status(db, item.id)
    # La solicitud y este registro ya están confirmados. Una reclamación durable
    # precede a cualquier I/O: ni un timeout ni un reinicio permiten repetir SMTP.
    try:
        claimed = db.execute(update(CommercialApplicationNotification).where(
            CommercialApplicationNotification.application_id == item.id,
            CommercialApplicationNotification.status == 'pending').values(
                status='sending', attempted_at=datetime.now(timezone.utc).replace(tzinfo=None)))
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.warning('commercial_owner_notification_claim_unavailable')
        return 'sending'
    if claimed.rowcount != 1:
        return status(db, item.id)
    result, error_code = 'failed', None
    try:
        config = configuration()
        message = message_for(item, config)
    except Exception:
        error_code = 'configuration_error'
    else:
        try:
            await run_in_threadpool(send, config, message)
            result = 'sent'  # El servidor SMTP aceptó el mensaje; no acredita recepción en buzón.
        except Exception:
            error_code = 'smtp_error'
    if error_code:
        logger.warning('commercial_owner_notification_failed: %s', error_code)
    try:
        db.execute(update(CommercialApplicationNotification).where(
            CommercialApplicationNotification.application_id == item.id).values(
                status=result, error_code=error_code, completed_at=datetime.now(timezone.utc).replace(tzinfo=None)))
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.warning('commercial_owner_notification_result_unrecorded')
        return 'sending'  # Resultado incierto: no reenviar automáticamente.
    return result
