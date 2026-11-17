"""Identidades IoT empresariales; las credenciales solo se almacenan como hash."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base
from .organization_scope import OrganizationScoped


class IotStation(OrganizationScoped, Base):
    __tablename__ = 'iot_stations'
    __table_args__ = (UniqueConstraint('organization_id', 'code', name='uq_iot_station_code'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class IotDevice(OrganizationScoped, Base):
    __tablename__ = 'iot_devices'
    __table_args__ = (UniqueConstraint('organization_id', 'device_id', name='uq_iot_device_code'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    station_id: Mapped[int] = mapped_column(ForeignKey('iot_stations.id'), index=True)
    device_id: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    credential_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
