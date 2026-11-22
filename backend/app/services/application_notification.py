"""SMTP opcional y acotado; como máximo un intento por solicitud, sin reenvío ambiguo."""
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
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


def configuration():
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
    return Configuration(host, port, security, normalized_email(os.getenv('AGROSCAN_SMTP_FROM', '')),
        normalized_email(os.getenv('AGROSCAN_COMMERCIAL_OWNER_EMAIL', '')), username, password)


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
    transport = smtplib.SMTP_SSL(config.host, config.port, timeout=5, context=context) if config.security == 'ssl' else smtplib.SMTP(config.host, config.port, timeout=5)
    with transport as smtp:
        if config.security == 'starttls':
            smtp.ehlo(); smtp.starttls(context=context); smtp.ehlo()
        if config.username:
            smtp.login(config.username, config.password)
        if smtp.send_message(message):
            raise smtplib.SMTPException('Recipient not accepted')


async def notify_once(db, item):
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
