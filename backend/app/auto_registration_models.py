"""AG-053: resultado preliminar de YOLOE, sin clasificación E0/E1/E2.

El token de una detección autorizada se consume una sola vez; un reintento
con el mismo token devuelve la evaluación original y no crea otra pieza.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VisionPrecheck(Base):
    __tablename__ = 'vision_prechecks'

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False, index=True)
    product: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    image_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    # Incrementar antes de buscar el siguiente código obtiene un bloqueo de
    # escritura SQLite, serializando registros simultáneos sin tabla secuencial.
    registration_claims: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    registered_lot_id: Mapped[int | None] = mapped_column(ForeignKey('lots.id'), nullable=True)
    evaluation_id: Mapped[int | None] = mapped_column(ForeignKey('evaluations.id'), nullable=True)
