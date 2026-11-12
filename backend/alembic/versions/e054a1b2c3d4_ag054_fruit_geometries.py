"""AG-054: persistir medidas geometricas por evidencia RGB, sin afectar historicos.

Revision ID: e054a1b2c3d4
Revises: d50b9a0e53aa
"""
from alembic import op
import sqlalchemy as sa

revision = 'e054a1b2c3d4'
down_revision = 'd50b9a0e53aa'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'fruit_geometries',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('evaluation_id', sa.Integer, sa.ForeignKey('evaluations.id'), nullable=False),
        sa.Column('image_id', sa.Integer, sa.ForeignKey('images.id'), nullable=False),
        sa.Column('image_sha256', sa.String(64), nullable=False),
        sa.Column('model_version', sa.String(100), nullable=False),
        sa.Column('rules_version', sa.String(64), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('reason', sa.String(64), nullable=False),
        sa.Column('product', sa.String(20), nullable=True),
        sa.Column('confidence', sa.Float, nullable=True),
        sa.Column('candidate_count', sa.Integer, nullable=False),
        sa.Column('frame_width', sa.Integer, nullable=False),
        sa.Column('frame_height', sa.Integer, nullable=False),
        sa.Column('box_json', sa.Text, nullable=False),
        sa.Column('polygon_json', sa.Text, nullable=False),
        sa.Column('measurements_json', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('image_id','image_sha256','model_version','rules_version',
                            name='uq_ag054_image_geometry_version'),
    )
    op.create_index('ix_fruit_geometries_evaluation_id', 'fruit_geometries', ['evaluation_id'])
    op.create_index('ix_fruit_geometries_image_id', 'fruit_geometries', ['image_id'])


def downgrade():
    op.drop_index('ix_fruit_geometries_image_id', table_name='fruit_geometries')
    op.drop_index('ix_fruit_geometries_evaluation_id', table_name='fruit_geometries')
    op.drop_table('fruit_geometries')
