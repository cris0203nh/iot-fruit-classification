"""Solicitudes globales previas a empresa. No confieren membresías ni contratos."""
from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


class CommercialApplication(Base):
    __tablename__ = 'commercial_applications'
    __table_args__ = (
        CheckConstraint("status IN ('pending','under_review','approved','rejected')", name='ck_application_status'),
        CheckConstraint("requested_period IN ('monthly','annual')", name='ck_application_period'),
        Index('uq_application_open_payload', 'payload_hash', unique=True,
              sqlite_where=text("status IN ('pending','under_review')")),
        Index('ix_application_status_created', 'status', 'created_at'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_name: Mapped[str] = mapped_column(String(120))
    contact_name: Mapped[str] = mapped_column(String(120))
    contact_email: Mapped[str] = mapped_column(String(254))
    requested_plan_id: Mapped[int] = mapped_column(ForeignKey('commercial_plans.id'))
    requested_period: Mapped[str] = mapped_column(String(10))
    plan_snapshot_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    source: Mapped[str] = mapped_column(String(20), default='public_web')
    idempotency_hash: Mapped[str] = mapped_column(String(64), unique=True)
    payload_hash: Mapped[str] = mapped_column(String(64))


class CommercialApplicationAttempt(Base):
    __tablename__ = 'commercial_application_attempts'
    __table_args__ = (Index('ix_application_attempt_bucket', 'bucket_hash', 'created_at'),
                      Index('ix_application_attempt_created', 'created_at'))
    id: Mapped[int] = mapped_column(primary_key=True)
    bucket_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class CommercialApplicationNotification(Base):
    """Estado mínimo de un intento SMTP; nunca guarda cuerpo, dirección o credenciales."""
    __tablename__ = 'commercial_application_notifications'
    __table_args__ = (CheckConstraint("status IN ('pending','sending','sent','failed','disabled')", name='ck_application_notification_status'),)
    application_id: Mapped[str] = mapped_column(ForeignKey('commercial_applications.id'), primary_key=True)
    status: Mapped[str] = mapped_column(String(10))
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_code: Mapped[str | None] = mapped_column(String(30))


class CommercialApplicationDecision(Base):
    """Historial del propietario; aprobación fija empresa/propuesta, nunca acceso."""
    __tablename__ = 'commercial_application_decisions'
    __table_args__ = (
        CheckConstraint("action IN ('review','approve','reject')", name='ck_application_decision_action'),
        CheckConstraint("(action = 'approve' AND organization_id IS NOT NULL AND organization_identity IS NOT NULL) OR (action != 'approve' AND organization_id IS NULL AND organization_identity IS NULL)", name='ck_application_decision_company'),
        UniqueConstraint('application_id', 'idempotency_hash', name='uq_application_decision_key'),
        UniqueConstraint('application_id', 'action', name='uq_application_decision_action'),
        Index('uq_application_terminal_decision', 'application_id', unique=True,
              sqlite_where=text("action IN ('approve','reject')")),
        Index('uq_application_approved_company', 'application_id', 'organization_id', unique=True),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[str] = mapped_column(ForeignKey('commercial_applications.id'))
    action: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str] = mapped_column(String(1000))
    actor_user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey('organizations.id'), unique=True)
    organization_identity: Mapped[str | None] = mapped_column(String(240), unique=True)
    idempotency_hash: Mapped[str] = mapped_column(String(64))
    payload_hash: Mapped[str] = mapped_column(String(64))


class CommercialApplicationInvitation(Base):
    """Procedencia platform_owner; las invitaciones legacy conservan sus reglas."""
    __tablename__ = 'commercial_application_invitations'
    __table_args__ = (
        ForeignKeyConstraint(['application_id', 'organization_id'],
            ['commercial_application_decisions.application_id', 'commercial_application_decisions.organization_id']),
        ForeignKeyConstraint(['organization_id', 'invitation_id'],
            ['organization_invitations.organization_id', 'organization_invitations.id']),
        UniqueConstraint('application_id', 'issued_key_hash', name='uq_initial_invitation_key'),
        Index('uq_initial_invitation_current', 'application_id', unique=True, sqlite_where=text('is_current = 1')),
        Index('uq_initial_invitation_trace', 'application_id', 'organization_id', 'invitation_id', unique=True),
    )
    invitation_id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[str] = mapped_column(String(36))
    organization_id: Mapped[int] = mapped_column()
    issued_key_hash: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    revoked_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
