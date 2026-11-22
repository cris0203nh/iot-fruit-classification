"""Procedencia y relaciones de invitación inicial; no reescribe SaaS-06."""
from alembic import op
import sqlalchemy as sa

revision = 'c012initialadmin'
down_revision = 'c011decisions'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql('BEGIN IMMEDIATE')
    op.create_index('uq_application_approved_company', 'commercial_application_decisions',
                    ['application_id', 'organization_id'], unique=True)
    op.create_table('commercial_application_invitations',
        sa.Column('invitation_id', sa.Integer, primary_key=True),
        sa.Column('application_id', sa.String(36), nullable=False),
        sa.Column('organization_id', sa.Integer, nullable=False),
        sa.Column('issued_key_hash', sa.String(64), nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('is_current', sa.Boolean, nullable=False),
        sa.Column('revoked_by', sa.Integer, sa.ForeignKey('users.id')),
        sa.ForeignKeyConstraint(['application_id','organization_id'],
            ['commercial_application_decisions.application_id','commercial_application_decisions.organization_id']),
        sa.ForeignKeyConstraint(['organization_id','invitation_id'],
            ['organization_invitations.organization_id','organization_invitations.id']),
        sa.UniqueConstraint('application_id','issued_key_hash',name='uq_initial_invitation_key'))
    op.create_index('uq_initial_invitation_current','commercial_application_invitations',['application_id'],
                    unique=True,sqlite_where=sa.text('is_current = 1'))


def downgrade():
    bind = op.get_bind()
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql('BEGIN IMMEDIATE')
    if bind.exec_driver_sql('SELECT count(*) FROM commercial_application_invitations').scalar():
        raise RuntimeError('No se revierte COM-04 con invitaciones iniciales; conservar procedencia y auditoría.')
    op.drop_table('commercial_application_invitations')
    op.drop_index('uq_application_approved_company', table_name='commercial_application_decisions')
