"""AG-037: append-only snapshots of automatic fruit detection, distinct from human reviews."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class VisionAssessment(Base):
    __tablename__ = 'vision_assessments'
    __table_args__ = (UniqueConstraint('image_id', 'image_sha256', 'rules_version',
                                       'model_version', name='uq_vision_image_model_rules'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey('evaluations.id'), nullable=False, index=True)
    image_id: Mapped[int] = mapped_column(ForeignKey('images.id'), nullable=False, index=True)
    image_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    rules_version: Mapped[str] = mapped_column(String(64), nullable=False)
    inference_size: Mapped[int] = mapped_column(Integer, nullable=False)
    inference_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    acceptance_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    detections_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                default=lambda: datetime.now(timezone.utc), nullable=False)
