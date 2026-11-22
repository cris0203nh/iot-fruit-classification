"""Sesiones privadas revocables; no modifica usuarios ni datos operativos."""
from alembic import op
import sqlalchemy as sa

revision = 'a016sessions'
down_revision = 'c015imagekey'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('browser_sessions',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('password_fingerprint', sa.String(64), nullable=False),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('absolute_expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_browser_sessions_user_id', 'browser_sessions', ['user_id'])


def downgrade():
    op.drop_index('ix_browser_sessions_user_id', table_name='browser_sessions')
    op.drop_table('browser_sessions')
