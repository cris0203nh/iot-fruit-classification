"""Privilegio del propietario: separado del catálogo de roles empresariales."""
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class PlatformOwner(Base):
    __tablename__ = 'platform_owner'
    __table_args__ = (CheckConstraint('id = 1', name='ck_platform_owner_singleton'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc), nullable=False)
