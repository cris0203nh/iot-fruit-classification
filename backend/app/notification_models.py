"""Outbox comercial global: acceso HTTP exclusivo del propietario."""
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


class CommercialNotification(Base):
    __tablename__ = 'commercial_notification_outbox'
    __table_args__ = (
        CheckConstraint("status IN ('pending','processing','smtp_accepted','retry_pending','failed','omitted')", name='ck_outbox_status'),
        CheckConstraint('attempts >= 0', name='ck_outbox_attempts'),
        Index('ix_outbox_due', 'status', 'next_attempt_at'),
        Index('ix_outbox_company_created', 'organization_id', 'created_at'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_key: Mapped[str] = mapped_column(String(240), unique=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey('organizations.id'))
    recipient_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    event: Mapped[str] = mapped_column(String(40))
    reference: Mapped[str] = mapped_column(String(120))
    recipient: Mapped[str | None] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(160))
    payload_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime)
    smtp_accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_code: Mapped[str | None] = mapped_column(String(40))
    claim_id: Mapped[str | None] = mapped_column(String(36))
