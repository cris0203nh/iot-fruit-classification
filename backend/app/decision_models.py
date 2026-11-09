"""AG-038: metadata for a decision already recorded in the canonical reviews log.

This is not a second review log: each row is a one-to-one, append-only
extension of Review with the inspected evidence and idempotency metadata.
"""
from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class ReviewDecisionEvidence(Base):
    __tablename__ = 'review_decision_evidence'
    __table_args__ = (
        UniqueConstraint('evaluation_id', 'request_id', name='uq_ag038_evaluation_request'),
    )

    review_id: Mapped[int] = mapped_column(ForeignKey('reviews.id'), primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey('evaluations.id'), nullable=False, index=True)
    image_id: Mapped[int] = mapped_column(ForeignKey('images.id'), nullable=False)
    image_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
