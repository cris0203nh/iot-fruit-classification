import secrets
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..database import get_db
from ..dependencies import require_admin
from ..identity_models import OrganizationInvitation
from ..models import Role, User
from ..user_schemas import RoleName
from ..services.google_identity import normalized_email
from ..services.invitations import aware, digest, now

router = APIRouter(prefix='/api/invitations', tags=['invitaciones'], dependencies=[Depends(require_admin)])


class InvitationCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(min_length=3, max_length=254)
    role: RoleName
    expiresHours: int = Field(default=48, ge=1, le=168)

    @field_validator('email')
    @classmethod
    def email_address(cls, value):
        return normalized_email(value)


def output(item, role):
    state = 'accepted' if item.accepted_at else 'revoked' if item.revoked_at else 'expired' if aware(item.expires_at) <= now() else 'pending'
    return {'id': item.id, 'email': item.email, 'role': role, 'expiresAt': aware(item.expires_at).isoformat(), 'status': state}


@router.get('')
def list_invitations(db: Session = Depends(get_db)):
    rows = db.execute(select(OrganizationInvitation, Role.name).join(Role,
        Role.id == OrganizationInvitation.role_id).order_by(OrganizationInvitation.id.desc())).all()
    return [output(item, role) for item, role in rows]


@router.post('', status_code=201)
def create_invitation(body: InvitationCreate, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    role = db.scalar(select(Role).where(Role.name == body.role))
    if role is None:
        raise HTTPException(409, 'Rol no registrado.')
    token = secrets.token_urlsafe(32)
    item = OrganizationInvitation(email=body.email, role_id=role.id, created_by=user.id,
        token_hash=digest(token), expires_at=now() + timedelta(hours=body.expiresHours))
    db.add(item)
    db.commit()
    return {**output(item, role.name), 'token': token}


@router.delete('/{invitation_id}', status_code=204)
def revoke_invitation(invitation_id: int, db: Session = Depends(get_db)):
    item = db.get(OrganizationInvitation, invitation_id)
    if item is None:
        raise HTTPException(404, 'Invitación no encontrada.')
    if item.accepted_at is not None:
        raise HTTPException(409, 'La invitación ya fue aceptada. Gestiona su membresía.')
    item.revoked_at = now()
    db.commit()
