"""AG-054: instantaneas inmutables de deteccion/medicion por evidencia RGB."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FruitGeometry(Base):
    __tablename__ = 'fruit_geometries'
    __table_args__ = (
        UniqueConstraint('image_id', 'image_sha256', 'model_version', 'rules_version',
                         name='uq_ag054_image_geometry_version'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey('evaluations.id'), nullable=False, index=True)
    image_id: Mapped[int] = mapped_column(ForeignKey('images.id'), nullable=False, index=True)
    image_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    rules_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    product: Mapped[str | None] = mapped_column(String(20), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    frame_width: Mapped[int] = mapped_column(Integer, nullable=False)
    frame_height: Mapped[int] = mapped_column(Integer, nullable=False)
    box_json: Mapped[str] = mapped_column(Text, nullable=False)
    polygon_json: Mapped[str] = mapped_column(Text, nullable=False)
    measurements_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
