from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Organization(Base):
    __tablename__ = 'organizations'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class OrganizationMembership(Base):
    __tablename__ = 'organization_memberships'
    organization_id: Mapped[int] = mapped_column(ForeignKey('organizations.id'), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), primary_key=True, index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey('roles.id'), primary_key=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
