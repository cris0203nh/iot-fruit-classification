"""AG-054 I02: mediciones geometricas proyectadas; NO dimensiones fisicas validadas."""
from datetime import datetime, timezone
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PlanarCalibration(Base):
    __tablename__ = 'ag054_planar_calibrations'
    __table_args__ = (UniqueConstraint('image_id', 'geometry_id', 'image_sha256',
                                       'marker_id', 'marker_side_mm', 'rules_version',
                                       name='uq_ag054_planar_reference'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey('evaluations.id'), nullable=False, index=True)
    image_id: Mapped[int] = mapped_column(ForeignKey('images.id'), nullable=False, index=True)
    geometry_id: Mapped[int] = mapped_column(ForeignKey('fruit_geometries.id'), nullable=False)
    operator_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    image_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    rules_version: Mapped[str] = mapped_column(String(64), nullable=False)
    marker_id: Mapped[int] = mapped_column(Integer, nullable=False)
    marker_side_mm: Mapped[float] = mapped_column(Float, nullable=False)
    platform_plane_declared: Mapped[bool] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(String(80), nullable=False)
    marker_corners_json: Mapped[str] = mapped_column(Text, nullable=False)
    measurements_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
