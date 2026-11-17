"""SaaS-06: identidades explícitas, desafíos Google e invitaciones; sin alterar históricos."""
from alembic import op
import sqlalchemy as sa

revision = 's006identity'
down_revision = 's004roles'
branch_labels = None
depends_on = None


def begin():
    bind = op.get_bind()
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql('BEGIN IMMEDIATE')
    return bind


def upgrade():
    begin()
    op.create_table('google_identities',
        sa.Column('subject', sa.String(255), primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False, unique=True),
        sa.Column('email', sa.String(254), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('google_challenges',
        sa.Column('cookie_hash', sa.String(64), primary_key=True),
        sa.Column('nonce_hash', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_google_challenges_expires_at', 'google_challenges', ['expires_at'])
    op.create_table('organization_invitations',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('organization_id', sa.Integer, sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('email', sa.String(254), nullable=False),
        sa.Column('role_id', sa.Integer, sa.ForeignKey('roles.id'), nullable=False),
        sa.Column('created_by', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('accepted_by', sa.Integer, sa.ForeignKey('users.id'), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('organization_id', 'id', name='uq_organization_invitations_org_pk'),
        sa.CheckConstraint('expires_at > created_at', name='ck_invitation_expiry'))
    op.create_index('ix_organization_invitations_expires_at', 'organization_invitations', ['expires_at'])


def downgrade():
    bind = begin()
    if bind.exec_driver_sql('SELECT 1 FROM google_identities LIMIT 1').first() or bind.exec_driver_sql('SELECT 1 FROM organization_invitations LIMIT 1').first():
        raise RuntimeError('Reversión bloqueada: existen identidades o invitaciones que deben conservarse.')
    op.drop_table('organization_invitations')
    op.drop_table('google_challenges')
    op.drop_table('google_identities')
