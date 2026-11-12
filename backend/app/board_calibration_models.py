"""AG-054 I03: evidencias append-only de referencias planas y contraste manual."""
from datetime import datetime, timezone
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BoardCalibration(Base):
    __tablename__ = 'ag054_board_calibrations'
    __table_args__ = (UniqueConstraint('image_id', 'geometry_id', 'image_sha256', 'rules_version',
                                       name='uq_ag054_board_snapshot'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey('evaluations.id'), nullable=False, index=True)
    image_id: Mapped[int] = mapped_column(ForeignKey('images.id'), nullable=False, index=True)
    geometry_id: Mapped[int] = mapped_column(ForeignKey('fruit_geometries.id'), nullable=False)
    operator_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    image_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    rules_version: Mapped[str] = mapped_column(String(64), nullable=False)
    board_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(String(80), nullable=False)
    marker_ids_json: Mapped[str] = mapped_column(Text, nullable=False)
    corners_json: Mapped[str] = mapped_column(Text, nullable=False)
    measurements_json: Mapped[str] = mapped_column(Text, nullable=False)
    rms_reprojection_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    platform_level_declared: Mapped[bool] = mapped_column(nullable=False)
    independent_support_declared: Mapped[bool] = mapped_column(nullable=False)
    printed_scale_verified_declared: Mapped[bool] = mapped_column(nullable=False)
    fixed_camera_declared: Mapped[bool] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class DimensionalComparison(Base):
    __tablename__ = 'ag054_dimensional_comparisons'
    __table_args__ = (UniqueConstraint('board_calibration_id', 'major_manual_cm', 'minor_manual_cm',
                                      'instrument_id', 'rules_version', name='uq_ag054_dimensional_reference'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    board_calibration_id: Mapped[int] = mapped_column(ForeignKey('ag054_board_calibrations.id'), nullable=False, index=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    rules_version: Mapped[str] = mapped_column(String(64), nullable=False)
    major_manual_cm: Mapped[float] = mapped_column(Float, nullable=False)
    minor_manual_cm: Mapped[float] = mapped_column(Float, nullable=False)
    instrument_id: Mapped[str] = mapped_column(String(120), nullable=False)
    comparison_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
