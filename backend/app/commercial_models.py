"""Suscripciones DEMO: independientes de membresías y permisos empresariales."""
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base
from .organization_scope import OrganizationScoped


class CommercialPlan(Base):
    __tablename__ = 'commercial_plans'
    __table_args__ = (
        UniqueConstraint('code', 'version', name='uq_commercial_plan_version'),
        CheckConstraint('amount_cents >= 0 AND amount_cents <= 100000000', name='ck_plan_price'),
        CheckConstraint("period IN ('monthly','annual') AND currency = 'PEN'", name='ck_plan_period'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40))
    version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500))
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default='PEN')
    period: Mapped[str] = mapped_column(String(10))
    benefits_json: Mapped[str] = mapped_column(Text)
    limits_json: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)
    recommended: Mapped[bool] = mapped_column(default=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, server_default='1')
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    creation_key: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    creation_payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    change_note: Mapped[str] = mapped_column(String(500), default='', server_default='')


class CommercialSubscription(OrganizationScoped, Base):
    __tablename__ = 'commercial_subscriptions'
    __table_args__ = (
        UniqueConstraint('organization_id', name='uq_subscription_company'),
        CheckConstraint("status IN ('active','cancelled')", name='ck_subscription_status'),
        CheckConstraint('ends_at > starts_at', name='ck_subscription_dates'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey('commercial_plans.id'))
    snapshot_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12))
    starts_at: Mapped[datetime] = mapped_column(DateTime)
    ends_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class CommercialOrder(OrganizationScoped, Base):
    __tablename__ = 'commercial_orders'
    __table_args__ = (
        UniqueConstraint('organization_id', 'idempotency_key', name='uq_order_idempotency'),
        CheckConstraint("status IN ('pending','demo_approved','demo_rejected','cancelled')", name='ck_order_status'),
        CheckConstraint("action IN ('subscribe','change','renew')", name='ck_order_action'),
        CheckConstraint('amount_cents >= 0', name='ck_order_price'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(80))
    plan_id: Mapped[int] = mapped_column(ForeignKey('commercial_plans.id'))
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    snapshot_json: Mapped[str] = mapped_column(Text)
    amount_cents: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class CommercialTransaction(OrganizationScoped, Base):
    __tablename__ = 'commercial_transactions'
    __table_args__ = (
        UniqueConstraint('order_id', name='uq_demo_transaction_order'),
        CheckConstraint("outcome IN ('demo_approved','demo_rejected','cancelled','subscription_cancelled')", name='ck_demo_outcome'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    outcome: Mapped[str] = mapped_column(String(24))
    amount_cents: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class CommercialOnboardingOrder(OrganizationScoped, Base):
    """Enlace aditivo; no fabrica contratación ni modifica órdenes legacy."""
    __tablename__ = 'commercial_onboarding_orders'
    __table_args__ = (
        ForeignKeyConstraint(['application_id', 'organization_id', 'invitation_id'],
            ['commercial_application_invitations.application_id', 'commercial_application_invitations.organization_id', 'commercial_application_invitations.invitation_id']),
        Index('uq_onboarding_completed', 'application_id', unique=True, sqlite_where=text('subscription_id IS NOT NULL')),
    )
    order_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    application_id: Mapped[str] = mapped_column(String(36))
    invitation_id: Mapped[int] = mapped_column(Integer)
    subscription_id: Mapped[int | None] = mapped_column(Integer)
    accepted_updated_plan: Mapped[bool] = mapped_column(Boolean, default=False)
