import hashlib
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select, update
from ..identity_models import OrganizationInvitation
from ..models import Role, User
from ..organization_models import Organization, OrganizationMembership


def now():
    return datetime.now(timezone.utc)


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def invitation_for_token(db, token):
    # Consulta por capacidad secreta, no por ID de empresa enviado por el cliente.
    table = OrganizationInvitation.__table__
    row = db.execute(select(table).where(table.c.token_hash == digest(token))).mappings().first()
    if row is None:
        raise HTTPException(404, 'Invitación no válida.')
    if row['accepted_at'] is not None or row['revoked_at'] is not None or aware(row['expires_at']) <= now():
        raise HTTPException(410, 'La invitación venció, fue utilizada o fue revocada.')
    organization = db.get(Organization, row['organization_id'])
    issuer = db.get(User, row['created_by'])
    authorized = db.scalar(select(OrganizationMembership.user_id).join(Role, Role.id == OrganizationMembership.role_id)
        .where(OrganizationMembership.organization_id == row['organization_id'],
               OrganizationMembership.user_id == row['created_by'], OrganizationMembership.is_active.is_(True),
               Role.name == 'administrador'))
    if organization is None or not organization.is_active or issuer is None or not issuer.is_active or authorized is None:
        raise HTTPException(403, 'La invitación ya no está autorizada.')
    role = db.get(Role, row['role_id'])
    if role is None or role.name not in ('administrador','operador','revisor'):
        raise HTTPException(403, 'Rol de invitación no permitido.')
    context = db.info.get('organization_id')
    if context is not None and context != organization.id:
        raise HTTPException(403, 'Invitación de otra empresa.')
    return row, organization, role


def grant_invitation(db, token, user):
    row, organization, role = invitation_for_token(db, token)
    if not user.is_active:
        raise HTTPException(401, 'Cuenta inactiva.')
    if db.scalar(select(OrganizationMembership.user_id).where(
            OrganizationMembership.organization_id == organization.id, OrganizationMembership.user_id == user.id)) is not None:
        raise HTTPException(409, 'Ya existe una membresía. Solicita al administrador los cambios de acceso.')
    db.info['organization_id'] = organization.id
    changed = db.execute(update(OrganizationInvitation).where(OrganizationInvitation.id == row['id'],
        OrganizationInvitation.accepted_at.is_(None), OrganizationInvitation.revoked_at.is_(None),
        OrganizationInvitation.expires_at > now()).values(accepted_at=now(), accepted_by=user.id))
    if changed.rowcount != 1:
        raise HTTPException(410, 'La invitación ya no está disponible.')
    db.add(OrganizationMembership(organization_id=organization.id, user_id=user.id, role_id=role.id))
    return organization.id
