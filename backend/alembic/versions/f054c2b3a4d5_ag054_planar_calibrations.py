"""AG-054 I02: guardar mediciones del plano ArUco sin alterar datos existentes.

Revision ID: f054c2b3a4d5
Revises: e054a1b2c3d4
"""
from alembic import op
import sqlalchemy as sa

revision = 'f054c2b3a4d5'
down_revision = 'e054a1b2c3d4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ag054_planar_calibrations',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('evaluation_id', sa.Integer, sa.ForeignKey('evaluations.id'), nullable=False),
        sa.Column('image_id', sa.Integer, sa.ForeignKey('images.id'), nullable=False),
        sa.Column('geometry_id', sa.Integer, sa.ForeignKey('fruit_geometries.id'), nullable=False),
        sa.Column('operator_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('image_sha256', sa.String(64), nullable=False),
        sa.Column('model_version', sa.String(100), nullable=False),
        sa.Column('rules_version', sa.String(64), nullable=False),
        sa.Column('marker_id', sa.Integer, nullable=False),
        sa.Column('marker_side_mm', sa.Float, nullable=False),
        sa.Column('platform_plane_declared', sa.Boolean, nullable=False),
        sa.Column('status', sa.String(40), nullable=False),
        sa.Column('reason', sa.String(80), nullable=False),
        sa.Column('marker_corners_json', sa.Text, nullable=False),
        sa.Column('measurements_json', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('image_id', 'geometry_id', 'image_sha256', 'marker_id',
                            'marker_side_mm', 'rules_version', name='uq_ag054_planar_reference'),
    )
    op.create_index('ix_ag054_planar_calibrations_evaluation_id', 'ag054_planar_calibrations', ['evaluation_id'])
    op.create_index('ix_ag054_planar_calibrations_image_id', 'ag054_planar_calibrations', ['image_id'])


def downgrade():
    op.drop_index('ix_ag054_planar_calibrations_image_id', table_name='ag054_planar_calibrations')
    op.drop_index('ix_ag054_planar_calibrations_evaluation_id', table_name='ag054_planar_calibrations')
    op.drop_table('ag054_planar_calibrations')
