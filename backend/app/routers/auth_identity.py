import hmac
import secrets
from datetime import timedelta
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session
from ..database import get_db
from ..dependencies import get_authenticated_identity
from ..identity_models import GoogleChallenge, GoogleIdentity
from ..models import User
from ..platform_models import PlatformOwner
from ..security import create_access_token, hash_password, verify_password
from ..services.google_identity import client_id, verify_google_token
from ..services.invitations import aware, digest, grant_invitation, invitation_for_token, now
from ..services.browser_sessions import issue_browser_session
from ..user_schemas import UserCreate

router = APIRouter(prefix='/api/auth', tags=['identidad-e-invitaciones'])
COOKIE = 'agroscan_google_challenge'
COOKIE_PATH = '/api/auth/google'


class SecretBody(BaseModel):
    model_config = ConfigDict(extra='forbid')


class TokenBody(SecretBody):
    token: str = Field(pattern=r'^[A-Za-z0-9_-]{43}$')


class InvitationAccept(TokenBody):
    password: str = Field(min_length=1, max_length=128)


class InvitationRegister(TokenBody):
    username: str = Field(min_length=3, max_length=64)
    fullName: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=12, max_length=128)

    @field_validator('username')
    @classmethod
    def username_value(cls, value):
        value = UserCreate.clean_username(value)
        if len(value) < 3:
            raise ValueError('Usuario demasiado corto.')
        return value

    @field_validator('fullName')
    @classmethod
    def name_value(cls, value):
        value = UserCreate.clean_name(value)
        if len(value) < 2:
            raise ValueError('Nombre demasiado corto.')
        return value


class GoogleCredential(SecretBody):
    credential: str = Field(min_length=1, max_length=8192)


class GoogleLink(GoogleCredential):
    password: str = Field(min_length=1, max_length=128)


class GoogleInvitation(GoogleCredential):
    token: str = Field(pattern=r'^[A-Za-z0-9_-]{43}$')


def payload(db, user, request, response, organization_id=None):
    persisted = issue_browser_session(db, user, request, response, organization_id)
    if persisted is not None:
        return persisted
    owner = db.get(PlatformOwner, 1)
    result = {'access_token': create_access_token(user.id), 'token_type': 'bearer',
              'is_superadmin': owner is not None and owner.user_id == user.id}
    if organization_id is not None:
        result['organization_id'] = organization_id
    return result


def begin(db):
    db.connection().exec_driver_sql('BEGIN IMMEDIATE')


def google_proof(db, request, credential):
    cookie = request.cookies.get(COOKIE, '')
    if len(cookie) != 43:
        raise HTTPException(401, 'Desafío de Google no válido.')
    challenge = db.get(GoogleChallenge, digest(cookie))
    if challenge is None or challenge.used_at is not None or aware(challenge.expires_at) <= now():
        raise HTTPException(401, 'Desafío de Google vencido o utilizado.')
    claims = verify_google_token(credential)
    if not hmac.compare_digest(challenge.nonce_hash, digest(claims['nonce'])):
        raise HTTPException(401, 'Desafío de Google no válido.')
    return claims, challenge.cookie_hash


def consume_challenge(db, cookie_hash):
    result = db.execute(update(GoogleChallenge).where(GoogleChallenge.cookie_hash == cookie_hash,
        GoogleChallenge.used_at.is_(None), GoogleChallenge.expires_at > now()).values(used_at=now()))
    if result.rowcount != 1:
        raise HTTPException(401, 'Desafío de Google vencido o utilizado.')


@router.get('/google/config')
def google_config():
    return {'enabled': bool(client_id()), 'clientId': client_id() or None}


@router.post('/google/challenge')
def google_challenge(request: Request, response: Response, intent: str | None = Header(default=None, alias='X-AgroScan-Intent'),
                     db: Session = Depends(get_db)):
    if not client_id():
        raise HTTPException(503, 'Google no está configurado. Usa el acceso tradicional.')
    if intent != 'google':
        raise HTTPException(403, 'Solicitud de Google no válida.')
    cookie, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.execute(delete(GoogleChallenge).where(GoogleChallenge.expires_at <= now()))
    previous = request.cookies.get(COOKIE)
    if previous:
        db.execute(delete(GoogleChallenge).where(GoogleChallenge.cookie_hash == digest(previous)))
    db.add(GoogleChallenge(cookie_hash=digest(cookie), nonce_hash=digest(nonce), expires_at=now()+timedelta(minutes=5)))
    db.commit()
    response.set_cookie(COOKIE, cookie, httponly=True, secure=request.url.scheme == 'https',
                        samesite='strict', max_age=300, path=COOKIE_PATH)
    response.headers['Cache-Control'] = 'no-store'
    return {'nonce': nonce}


@router.post('/google/login')
def google_login(body: GoogleCredential, request: Request, response: Response, db: Session = Depends(get_db)):
    claims, challenge = google_proof(db, request, body.credential)
    begin(db)
    consume_challenge(db, challenge)
    identity = db.get(GoogleIdentity, claims['sub'])
    if identity is None:
        raise HTTPException(403, 'Vincula Google desde tu cuenta o acepta una invitación. No se enlazan cuentas por correo.')
    user = db.get(User, identity.user_id)
    if user is None or not user.is_active:
        raise HTTPException(401, 'Cuenta inactiva.')
    identity.email = claims['email']
    db.commit()
    response.delete_cookie(COOKIE, path=COOKIE_PATH)
    return payload(db, user, request, response)


@router.post('/google/link')
def google_link(body: GoogleLink, request: Request, response: Response, db: Session = Depends(get_db),
                user: User = Depends(get_authenticated_identity)):
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(401, 'Confirma la contraseña de tu cuenta actual.')
    claims, challenge = google_proof(db, request, body.credential)
    begin(db)
    consume_challenge(db, challenge)
    identity = db.get(GoogleIdentity, claims['sub'])
    current = db.scalar(select(GoogleIdentity).where(GoogleIdentity.user_id == user.id))
    if (identity is not None and identity.user_id != user.id) or (current is not None and current.subject != claims['sub']):
        raise HTTPException(409, 'La identidad ya está vinculada. No se reasignan identidades automáticamente.')
    if identity is None:
        db.add(GoogleIdentity(subject=claims['sub'], user_id=user.id, email=claims['email']))
    db.commit()
    response.delete_cookie(COOKIE, path=COOKIE_PATH)
    return {'linked': True}


@router.post('/invitations/preview')
def invitation_preview(body: TokenBody, response: Response, db: Session = Depends(get_db)):
    row, organization, role = invitation_for_token(db, body.token)
    response.headers['Cache-Control'] = 'no-store'
    return {'email': row['email'], 'organizationName': organization.name, 'role': role.name,
            'expiresAt': aware(row['expires_at']).isoformat()}


@router.post('/invitations/accept')
def invitation_accept(body: InvitationAccept, request: Request, response: Response, db: Session = Depends(get_db), user: User = Depends(get_authenticated_identity)):
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(401, 'Confirma la contraseña de tu cuenta actual.')
    begin(db)
    organization_id = grant_invitation(db, body.token, user)
    db.commit()
    response.headers['Cache-Control'] = 'no-store'
    return payload(db, user, request, response, organization_id)


@router.post('/invitations/register', status_code=201)
def invitation_register(body: InvitationRegister, request: Request, response: Response, db: Session = Depends(get_db)):
    # Reutiliza normalización y validaciones locales; el rol proviene exclusivamente de la invitación.
    invitation_for_token(db, body.token)
    hashed = hash_password(body.password)
    begin(db)
    invitation_for_token(db, body.token)
    if db.scalar(select(User.id).where(User.username == body.username)) is not None:
        raise HTTPException(409, 'El usuario ya existe. Inicia sesión para aceptar explícitamente la invitación.')
    user = User(username=body.username, full_name=body.fullName, password_hash=hashed, is_active=True)
    db.add(user)
    db.flush()
    organization_id = grant_invitation(db, body.token, user)
    db.commit()
    response.headers['Cache-Control'] = 'no-store'
    return payload(db, user, request, response, organization_id)


@router.post('/google/accept-invitation')
def google_accept_invitation(body: GoogleInvitation, request: Request, response: Response, db: Session = Depends(get_db)):
    claims, challenge = google_proof(db, request, body.credential)
    preview, _, _ = invitation_for_token(db, body.token)
    if not hmac.compare_digest(preview['email'].encode(), claims['email'].encode()):
        raise HTTPException(403, 'La cuenta Google no coincide con el correo invitado.')
    random_password = hash_password(secrets.token_urlsafe(48))
    begin(db)
    consume_challenge(db, challenge)
    invitation, _, _ = invitation_for_token(db, body.token)
    if not hmac.compare_digest(invitation['email'].encode(), claims['email'].encode()):
        raise HTTPException(403, 'La cuenta Google no coincide con el correo invitado.')
    identity = db.get(GoogleIdentity, claims['sub'])
    if identity is not None:
        user = db.get(User, identity.user_id)
    else:
        # Nunca buscar ni fusionar usuarios por coincidencia de correo.
        name = claims.get('name')
        name = name if isinstance(name, str) and name.strip() else claims['email']
        user = User(username='google-'+secrets.token_hex(16), full_name=name[:120],
                    password_hash=random_password, is_active=True)
        db.add(user)
        db.flush()
        db.add(GoogleIdentity(subject=claims['sub'], user_id=user.id, email=claims['email']))
    if user is None:
        raise HTTPException(401, 'Cuenta no disponible.')
    organization_id = grant_invitation(db, body.token, user)
    db.commit()
    response.delete_cookie(COOKIE, path=COOKIE_PATH)
    response.headers['Cache-Control'] = 'no-store'
    return payload(db, user, request, response, organization_id)
