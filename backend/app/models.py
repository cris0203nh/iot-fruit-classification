from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Lot(Base):
    __tablename__ = "lots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    product: Mapped[str] = mapped_column(String(20))  # mango | tomate
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | closed
    responsible: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"), index=True)
    piece_id: Mapped[str] = mapped_column(String(64), index=True)
    product: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="processing")
    weight_grams: Mapped[float | None] = mapped_column(Float, nullable=True)
    image_count: Mapped[int] = mapped_column(Integer, default=0)
    visual_category: Mapped[str | None] = mapped_column(String(50), nullable=True)  # ORIGINAL, no se modifica
    review_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    calibration_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rules_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    weight_pre_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_pre_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    weight_post_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_post_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    boot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    lot: Mapped[Lot] = relationship()
    reviews: Mapped[list["Review"]] = relationship(
        back_populates="evaluation", order_by="Review.id"
    )


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id"), index=True)
    type: Mapped[str] = mapped_column(String(20))  # review | cancellation
    actor_id: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(500))
    previous_value: Mapped[str | None] = mapped_column(String(50), nullable=True)
    updated_value: Mapped[str | None] = mapped_column(String(50), nullable=True)
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    evaluation: Mapped[Evaluation] = relationship(back_populates="reviews")



class Measurement(Base):
    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    boot_id: Mapped[str] = mapped_column(String(64))
    seq: Mapped[int] = mapped_column(Integer)
    weight_g: Mapped[float] = mapped_column(Float)
    stable: Mapped[bool] = mapped_column(Boolean)
    calibration_version: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("device_id", "boot_id", "seq", name="uq_measurement_seq"),
    )


