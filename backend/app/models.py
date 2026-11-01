
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Lot(Base):
    __tablename__ = "lots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    product: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="open")
    responsible: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    pieces: Mapped[list["Piece"]] = relationship(back_populates="lot")
    evaluations: Mapped[list["Evaluation"]] = relationship(back_populates="lot")


class Piece(Base):
    __tablename__ = "pieces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lot_id: Mapped[int] = mapped_column(
        ForeignKey("lots.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="registered")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    lot: Mapped["Lot"] = relationship(back_populates="pieces")
    evaluations: Mapped[list["Evaluation"]] = relationship(back_populates="piece")

    __table_args__ = (
        UniqueConstraint("lot_id", "code", name="uq_piece_lot_code"),
    )


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"), index=True)

    # Identificador público conservado por compatibilidad con el frontend.
    piece_id: Mapped[str] = mapped_column(String(64), index=True)

    # Nueva relación normalizada con la entidad Piece.
    piece_ref_id: Mapped[int | None] = mapped_column(
        ForeignKey("pieces.id"), nullable=True, index=True
    )

    product: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="processing")
    weight_grams: Mapped[float | None] = mapped_column(Float, nullable=True)
    image_count: Mapped[int] = mapped_column(Integer, default=0)
    visual_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    review_note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    calibration_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rules_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    weight_pre_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_pre_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    weight_post_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_post_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    weight_pre_measurement_id: Mapped[int | None] = mapped_column(
        ForeignKey("measurements.id"), nullable=True
    )
    weight_post_measurement_id: Mapped[int | None] = mapped_column(
        ForeignKey("measurements.id"), nullable=True
    )

    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    boot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    lot: Mapped["Lot"] = relationship(back_populates="evaluations")
    piece: Mapped["Piece | None"] = relationship(back_populates="evaluations")

    images: Mapped[list["Image"]] = relationship(
        back_populates="evaluation", order_by="Image.id"
    )
    reviews: Mapped[list["Review"]] = relationship(
        back_populates="evaluation", order_by="Review.id"
    )

    weight_pre_measurement: Mapped["Measurement | None"] = relationship(
        foreign_keys=[weight_pre_measurement_id]
    )
    weight_post_measurement: Mapped["Measurement | None"] = relationship(
        foreign_keys=[weight_post_measurement_id]
    )


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
    zero_confirmed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("device_id", "boot_id", "seq", name="uq_measurement_seq"),
    )


class Image(Base):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[int] = mapped_column(
        ForeignKey("evaluations.id"), index=True
    )
    view: Mapped[str] = mapped_column(String(30))
    relative_path: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(30))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    evaluation: Mapped["Evaluation"] = relationship(back_populates="images")


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[int] = mapped_column(
        ForeignKey("evaluations.id"), index=True
    )
    type: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(500))
    previous_value: Mapped[str | None] = mapped_column(String(50), nullable=True)
    updated_value: Mapped[str | None] = mapped_column(String(50), nullable=True)
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    evaluation: Mapped["Evaluation"] = relationship(back_populates="reviews")
# Relación entre usuarios y roles.
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    username: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    full_name: Mapped[str] = mapped_column(
        String(120), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    roles: Mapped[list["Role"]] = relationship(
        secondary=user_roles,
        back_populates="users",
    )


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(
        String(30), unique=True, nullable=False
    )

    users: Mapped[list["User"]] = relationship(
        secondary=user_roles,
        back_populates="roles",
    )