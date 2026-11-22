"""Cookie opaca persistente; JWT y CSRF solo en memoria del cliente."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
import os

from fastapi import HTTPException, Request
from ..identity_models import BrowserSession
from ..models import User
from ..platform_models import PlatformOwner
from ..security import JWT_SECRET, create_access_token

COOKIE = 'agroscan_session'
IDLE = timedelta(days=7)
LIFETIME = timedelta(days=30)


def now():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_token(cookie):
    return hmac.new(JWT_SECRET.encode(), ('csrf:' + cookie).encode(), hashlib.sha256).hexdigest()


def local_http(request):
    # No se aceptan cabeceras Forwarded para habilitar HTTP ni hosts LAN.
    return (os.getenv('AGROSCAN_SESSION_ALLOW_LOOPBACK_HTTP') == 'true'
            and request.url.scheme == 'http' and request.url.hostname in ('127.0.0.1', 'localhost', '::1')
            and request.client is not None and request.client.host in ('127.0.0.1', '::1'))


def protect_browser_request(request: Request):
    cookie = request.cookies.get(COOKIE)
    browser = request.headers.get('X-AgroScan-Session') == 'browser'
    if (cookie or browser) and request.url.scheme != 'https' and not local_http(request):
        raise HTTPException(400, 'La sesión persistente requiere HTTPS o desarrollo/QA en loopback habilitado explícitamente.')
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return
    if request.url.path in ('/api/commercial/applications', '/api/auth/invitations/preview'):
        return  # Operaciones publicas sin autoridad derivada de la cookie.
    if not cookie and not browser:
        return  # Mantiene clientes Bearer/IoT sin autenticacion ambiental.
    origin = request.headers.get('origin')
    own = str(request.base_url).rstrip('/')
    allowed = {own, *[s.strip().rstrip('/') for s in os.getenv('AGROSCAN_DEMO_ORIGINS', '').split(',') if s.strip().startswith('https://')]}
    parsed = urlsplit(origin or '')
    loopback_origin = local_http(request) and parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost', '::1')
    if request.headers.get('sec-fetch-site') == 'cross-site' or (origin and origin not in allowed and not loopback_origin):
        raise HTTPException(403, 'Origen de sesion no autorizado.')
    bootstrap = request.url.path in (
        '/api/auth/login', '/api/auth/google/challenge', '/api/auth/google/login',
        '/api/auth/google/accept-invitation', '/api/auth/invitations/register')
    if bootstrap and browser:
        return  # Cabecera no simple + comprobacion de Origin evita login CSRF.
    if cookie and not hmac.compare_digest(request.headers.get('X-CSRF-Token', ''), csrf_token(cookie)):
        raise HTTPException(403, 'Proteccion CSRF: vuelve a validar tu sesion.')


def valid_session(db, key):
    row = db.get(BrowserSession, key, populate_existing=True)
    user = db.get(User, row.user_id, populate_existing=True) if row else None
    if (row is None or row.revoked_at is not None or aware(row.expires_at) <= now()
            or aware(row.absolute_expires_at) <= now() or user is None or not user.is_active
            or not hmac.compare_digest(row.password_fingerprint, digest(user.password_hash))):
        raise HTTPException(401, 'Sesion vencida o revocada.')
    return row, user


def cookie_session(db, request):
    cookie = request.cookies.get(COOKIE, '')
    if len(cookie) != 43:
        raise HTTPException(401, 'Inicia sesion nuevamente.')
    return valid_session(db, digest(cookie))


def output(db, row, user, cookie):
    owner = db.get(PlatformOwner, 1)
    result = {'access_token': create_access_token(user.id, session_id=row.token_hash),
              'token_type': 'bearer', 'is_superadmin': owner is not None and owner.user_id == user.id,
              'csrf_token': csrf_token(cookie), 'session_expires_at': aware(row.expires_at).isoformat()}
    if row.organization_id is not None:
        result['organization_id'] = row.organization_id
    return result


def set_cookie(request, response, cookie, expires):
    response.set_cookie(COOKIE, cookie, httponly=True, secure=not local_http(request),
        samesite='strict', path='/api', max_age=max(0, int((aware(expires) - now()).total_seconds())))
    response.headers['Cache-Control'] = 'no-store'


def issue_browser_session(db, user, request, response, organization_id=None):
    if request.headers.get('X-AgroScan-Session') != 'browser':
        return None
    if request.url.scheme != 'https' and not local_http(request):
        raise HTTPException(400, 'La sesión persistente requiere HTTPS o desarrollo/QA en loopback habilitado explícitamente.')
    previous = request.cookies.get(COOKIE)
    if previous:
        old = db.get(BrowserSession, digest(previous))
        if old is not None:
            old.revoked_at = now()
    cookie = secrets.token_urlsafe(32)
    row = BrowserSession(token_hash=digest(cookie), user_id=user.id,
        password_fingerprint=digest(user.password_hash), organization_id=organization_id,
        created_at=now(), expires_at=now()+IDLE, absolute_expires_at=now()+LIFETIME)
    db.add(row)
    db.commit()
    set_cookie(request, response, cookie, row.expires_at)
    return output(db, row, user, cookie)
