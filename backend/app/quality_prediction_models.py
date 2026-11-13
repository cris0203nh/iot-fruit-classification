"""AG-055: instantáneas experimentales, separadas de decisiones humanas."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class QualityPrediction(Base):
    __tablename__ = 'ag055_quality_predictions'
    __table_args__ = (UniqueConstraint('evaluation_id', 'source_fingerprint', 'model_sha256',
                                       name='uq_ag055_evaluation_source_model'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey('evaluations.id'), nullable=False, index=True)
    product: Mapped[str] = mapped_column(String(20), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    model_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(String(100), nullable=False)
    proposed_grade: Mapped[str | None] = mapped_column(String(2), nullable=True)
    details_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc))
