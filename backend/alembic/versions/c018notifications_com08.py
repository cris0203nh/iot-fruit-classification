"""Outbox aditivo, sin correos retroactivos ni cambios contractuales."""
from alembic import op
import sqlalchemy as sa

revision = 'c018notifications'
down_revision = 'c017catalog'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('commercial_notification_outbox',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('event_key', sa.String(240), nullable=False, unique=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id')),
        sa.Column('recipient_user_id', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('event', sa.String(40), nullable=False),
        sa.Column('reference', sa.String(120), nullable=False),
        sa.Column('recipient', sa.String(254)),
        sa.Column('subject', sa.String(160), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_attempt_at', sa.DateTime()),
        sa.Column('next_attempt_at', sa.DateTime()),
        sa.Column('smtp_accepted_at', sa.DateTime()),
        sa.Column('error_code', sa.String(40)),
        sa.Column('claim_id', sa.String(36)),
        sa.CheckConstraint("status IN ('pending','processing','smtp_accepted','retry_pending','failed','omitted')", name='ck_outbox_status'),
        sa.CheckConstraint('attempts >= 0', name='ck_outbox_attempts'))
    op.create_index('ix_outbox_due', 'commercial_notification_outbox', ['status', 'next_attempt_at'])
    op.create_index('ix_outbox_company_created', 'commercial_notification_outbox', ['organization_id', 'created_at'])


def downgrade():
    if op.get_bind().execute(sa.text('SELECT 1 FROM commercial_notification_outbox LIMIT 1')).first():
        raise RuntimeError('Outbox con auditoría: revertir solo mediante respaldo autorizado.')
    op.drop_table('commercial_notification_outbox')
