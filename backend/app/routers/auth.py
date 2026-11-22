from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import BUSINESS_ROLES, get_authenticated_identity, get_current_user
from ..platform_models import PlatformOwner
from ..models import User, Role
from ..organization_models import Organization, OrganizationMembership
from ..services.browser_sessions import (COOKIE, IDLE, cookie_session, digest,
    issue_browser_session, now, output, set_cookie, aware, local_http)
from ..identity_models import BrowserSession, GoogleChallenge
from sqlalchemy import update, func, delete
from ..security import (
    create_access_token,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["autenticacion"])


@router.post("/login")
def login(
    request: Request,
    response: Response,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.scalar(
        select(User).where(User.username == form.username)
    )

    if (
        user is None
        or not user.is_active
        or not verify_password(form.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    persisted = issue_browser_session(db, user, request, response)
    if persisted is not None:
        return persisted
    token = create_access_token(user.id)
    owner = db.get(PlatformOwner, 1)

    return {
        "access_token": token,
        "token_type": "bearer",
        "is_superadmin": owner is not None and owner.user_id == user.id,
    }


@router.get('/session')
def restore_session(request: Request, response: Response, db: Session = Depends(get_db)):
    row, user = cookie_session(db, request)
    response.headers['Cache-Control'] = 'no-store'
    return output(db, row, user, request.cookies[COOKIE])


@router.post('/session/refresh')
def refresh_session(request: Request, response: Response, db: Session = Depends(get_db)):
    row, user = cookie_session(db, request)
    # UPDATE condicionado: una renovacion concurrente nunca revive un logout.
    expiry = min(now() + IDLE, aware(row.absolute_expires_at))
    changed = db.execute(update(BrowserSession).where(BrowserSession.token_hash == row.token_hash,
        BrowserSession.revoked_at.is_(None), BrowserSession.expires_at > now(),
        BrowserSession.absolute_expires_at > now()).values(expires_at=func.max(BrowserSession.expires_at, expiry))
        .execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise HTTPException(401, 'Sesion vencida o revocada.')
    db.commit()
    db.refresh(row)
    set_cookie(request, response, request.cookies[COOKIE], row.expires_at)
    return output(db, row, user, request.cookies[COOKIE])


@router.put('/session/organization')
def select_session_organization(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.info.get('browser_session')
    if row is None:
        raise HTTPException(401, 'Se requiere una sesion de navegador.')
    changed = db.execute(update(BrowserSession).where(BrowserSession.token_hash == row.token_hash,
        BrowserSession.revoked_at.is_(None), BrowserSession.expires_at > now()).values(organization_id=db.info['organization_id'])
        .execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise HTTPException(401, 'Sesion vencida o revocada.')
    db.commit()
    return {'organizationId': db.info['organization_id']}


@router.post('/logout', status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    cookie = request.cookies.get(COOKIE)
    if not cookie:
        raise HTTPException(401, 'No hay una sesion de navegador activa.')
    if cookie:
        db.execute(update(BrowserSession).where(BrowserSession.token_hash == digest(cookie)).values(revoked_at=now()))
    challenge = request.cookies.get('agroscan_google_challenge')
    if challenge:
        db.execute(delete(GoogleChallenge).where(GoogleChallenge.cookie_hash == digest(challenge)))
    db.commit()
    response.delete_cookie(COOKIE, path='/api', secure=not local_http(request), httponly=True, samesite='strict')
    response.delete_cookie('agroscan_google_challenge', path='/api/auth/google',
        secure=not local_http(request), httponly=True, samesite='strict')
    response.headers['Cache-Control'] = 'no-store'


@router.get("/me")
def get_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    owner = db.get(PlatformOwner, 1)
    return {
        "id": current_user.id,
        "username": current_user.username,
        "fullName": current_user.full_name,
        "roles": sorted(db.info['organization_roles']),
        "organizationId": db.info['organization_id'],
        "organizations": db.info['organizations'],
        "isSuperadmin": owner is not None and owner.user_id == current_user.id,
    }


@router.get('/organizations')
def my_organizations(user: User = Depends(get_authenticated_identity), db: Session = Depends(get_db)):
    rows = db.execute(select(Organization.id, Organization.name, Role.name.label('role'))
        .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
        .join(Role, OrganizationMembership.role_id == Role.id)
        .where(OrganizationMembership.user_id == user.id,
               OrganizationMembership.is_active.is_(True), Organization.is_active.is_(True),
               Role.name.in_(BUSINESS_ROLES))
        .order_by(Organization.id, Role.name)).all()
    result = {}
    for row in rows:
        result.setdefault(row.id, {'id': row.id, 'name': row.name, 'roles': []})['roles'].append(row.role)
    return list(result.values())
