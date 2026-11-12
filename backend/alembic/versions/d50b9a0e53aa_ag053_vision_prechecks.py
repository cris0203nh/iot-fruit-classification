"""AG-053: detección previa e idempotencia del registro de piezas.

Revision ID: d50b9a0e53aa
Revises: b38c99a10246
"""
from alembic import op
import sqlalchemy as sa

revision = 'd50b9a0e53aa'
down_revision = 'b38c99a10246'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'vision_prechecks',
        sa.Column('token', sa.String(64), primary_key=True),
        sa.Column('operator_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('product', sa.String(20), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('image_sha256', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('registration_claims', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('registered_lot_id', sa.Integer(), sa.ForeignKey('lots.id'), nullable=True),
        sa.Column('evaluation_id', sa.Integer(), sa.ForeignKey('evaluations.id'), nullable=True),
    )
    op.create_index('ix_vision_prechecks_operator_id', 'vision_prechecks', ['operator_id'])


def downgrade():
    op.drop_index('ix_vision_prechecks_operator_id', table_name='vision_prechecks')
    op.drop_table('vision_prechecks')
