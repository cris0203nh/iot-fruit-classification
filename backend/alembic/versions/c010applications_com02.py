"""COM-02 solicitudes; no altera c009commerce ni aprovisiona empresas."""
from alembic import op
import sqlalchemy as sa

revision = 'c010applications'
down_revision = 'c009commerce'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql('BEGIN IMMEDIATE')
    op.create_table('commercial_applications',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('company_name', sa.String(120), nullable=False),
        sa.Column('contact_name', sa.String(120), nullable=False),
        sa.Column('contact_email', sa.String(254), nullable=False),
        sa.Column('requested_plan_id', sa.Integer, sa.ForeignKey('commercial_plans.id'), nullable=False),
        sa.Column('requested_period', sa.String(10), nullable=False),
        sa.Column('plan_snapshot_json', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('source', sa.String(20), nullable=False),
        sa.Column('idempotency_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('payload_hash', sa.String(64), nullable=False),
        sa.CheckConstraint("status IN ('pending','under_review','approved','rejected')", name='ck_application_status'),
        sa.CheckConstraint("requested_period IN ('monthly','annual')", name='ck_application_period'))
    op.create_index('uq_application_open_payload', 'commercial_applications', ['payload_hash'], unique=True,
                    sqlite_where=sa.text("status IN ('pending','under_review')"))
    op.create_index('ix_application_status_created', 'commercial_applications', ['status','created_at'])
    op.create_table('commercial_application_attempts', sa.Column('id', sa.Integer, primary_key=True),
                    sa.Column('bucket_hash', sa.String(64), nullable=False), sa.Column('created_at', sa.DateTime, nullable=False))
    op.create_index('ix_application_attempt_bucket', 'commercial_application_attempts', ['bucket_hash','created_at'])
    op.create_index('ix_application_attempt_created', 'commercial_application_attempts', ['created_at'])


def downgrade():
    bind = op.get_bind()
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql('BEGIN IMMEDIATE')
    op.drop_table('commercial_application_attempts')
    op.drop_table('commercial_applications')
