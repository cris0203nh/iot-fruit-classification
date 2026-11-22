"""Decisiones COM-03 aditivas; conserva solicitudes, empresas y c009/c010."""
from alembic import op
import sqlalchemy as sa

revision = 'c011decisions'
down_revision = 'c010applications'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql('BEGIN IMMEDIATE')
    op.create_table('commercial_application_decisions',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('application_id', sa.String(36), sa.ForeignKey('commercial_applications.id'), nullable=False),
        sa.Column('action', sa.String(10), nullable=False),
        sa.Column('reason', sa.String(1000), nullable=False),
        sa.Column('actor_user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('organization_id', sa.Integer, sa.ForeignKey('organizations.id'), unique=True),
        sa.Column('organization_identity', sa.String(240), unique=True),
        sa.Column('idempotency_hash', sa.String(64), nullable=False),
        sa.Column('payload_hash', sa.String(64), nullable=False),
        sa.CheckConstraint("action IN ('review','approve','reject')", name='ck_application_decision_action'),
        sa.CheckConstraint("(action = 'approve' AND organization_id IS NOT NULL AND organization_identity IS NOT NULL) OR (action != 'approve' AND organization_id IS NULL AND organization_identity IS NULL)", name='ck_application_decision_company'),
        sa.UniqueConstraint('application_id', 'idempotency_hash', name='uq_application_decision_key'),
        sa.UniqueConstraint('application_id', 'action', name='uq_application_decision_action'))
    op.create_index('uq_application_terminal_decision', 'commercial_application_decisions', ['application_id'],
                    unique=True, sqlite_where=sa.text("action IN ('approve','reject')"))


def downgrade():
    # Una decisión aplicada no se pierde dejando approved sin asociación/auditoría.
    bind = op.get_bind()
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql('BEGIN IMMEDIATE')
    if bind.exec_driver_sql('SELECT count(*) FROM commercial_application_decisions').scalar():
        raise RuntimeError('No se revierte COM-03 con decisiones registradas; restaurar respaldo aislado.')
    op.drop_table('commercial_application_decisions')
