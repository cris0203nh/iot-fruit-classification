"""SaaS-04: propietario global único, sin promociones automáticas.

Revision ID: s004roles
Revises: s003organizations
"""
from alembic import op
import sqlalchemy as sa

revision = 's004roles'
down_revision = 's003organizations'
branch_labels = None
depends_on = None


def _begin():
    bind = op.get_bind()
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql('BEGIN IMMEDIATE')
    return bind


def upgrade():
    _begin()
    op.create_table('platform_owner',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('id = 1', name='ck_platform_owner_singleton'),
        sa.UniqueConstraint('user_id'))
    # Ninguna cuenta histórica se promueve por ID, antigüedad o rol.


def downgrade():
    if _begin().exec_driver_sql('SELECT 1 FROM platform_owner LIMIT 1').first():
        raise RuntimeError('Reversión bloqueada: existe un propietario de plataforma asignado.')
    op.drop_table('platform_owner')
