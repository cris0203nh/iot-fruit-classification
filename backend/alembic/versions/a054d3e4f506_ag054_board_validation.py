"""AG-054 I03: tablero multimarcas y contraste con medidas de referencia.

Revision ID: a054d3e4f506
Revises: f054c2b3a4d5
"""
from alembic import op
import sqlalchemy as sa

revision = 'a054d3e4f506'
down_revision = 'f054c2b3a4d5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ag054_board_calibrations',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('evaluation_id', sa.Integer, sa.ForeignKey('evaluations.id'), nullable=False),
        sa.Column('image_id', sa.Integer, sa.ForeignKey('images.id'), nullable=False),
        sa.Column('geometry_id', sa.Integer, sa.ForeignKey('fruit_geometries.id'), nullable=False),
        sa.Column('operator_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('image_sha256', sa.String(64), nullable=False),
        sa.Column('model_version', sa.String(100), nullable=False),
        sa.Column('rules_version', sa.String(64), nullable=False),
        sa.Column('board_version', sa.String(64), nullable=False),
        sa.Column('status', sa.String(40), nullable=False),
        sa.Column('reason', sa.String(80), nullable=False),
        sa.Column('marker_ids_json', sa.Text, nullable=False),
        sa.Column('corners_json', sa.Text, nullable=False),
        sa.Column('measurements_json', sa.Text, nullable=False),
        sa.Column('rms_reprojection_mm', sa.Float, nullable=True),
        sa.Column('platform_level_declared', sa.Boolean, nullable=False),
        sa.Column('independent_support_declared', sa.Boolean, nullable=False),
        sa.Column('printed_scale_verified_declared', sa.Boolean, nullable=False),
        sa.Column('fixed_camera_declared', sa.Boolean, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('image_id','geometry_id','image_sha256','rules_version',
                            name='uq_ag054_board_snapshot'),
    )
    op.create_index('ix_ag054_board_calibrations_evaluation_id','ag054_board_calibrations',['evaluation_id'])
    op.create_index('ix_ag054_board_calibrations_image_id','ag054_board_calibrations',['image_id'])
    op.create_table(
        'ag054_dimensional_comparisons',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('board_calibration_id', sa.Integer, sa.ForeignKey('ag054_board_calibrations.id'), nullable=False),
        sa.Column('operator_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('rules_version', sa.String(64), nullable=False),
        sa.Column('major_manual_cm', sa.Float, nullable=False),
        sa.Column('minor_manual_cm', sa.Float, nullable=False),
        sa.Column('instrument_id', sa.String(120), nullable=False),
        sa.Column('comparison_json', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('board_calibration_id','major_manual_cm','minor_manual_cm',
                            'instrument_id','rules_version',name='uq_ag054_dimensional_reference'),
    )
    op.create_index('ix_ag054_dimensional_comparisons_board_calibration_id',
                    'ag054_dimensional_comparisons',['board_calibration_id'])


def downgrade():
    op.drop_index('ix_ag054_dimensional_comparisons_board_calibration_id',table_name='ag054_dimensional_comparisons')
    op.drop_table('ag054_dimensional_comparisons')
    op.drop_index('ix_ag054_board_calibrations_image_id',table_name='ag054_board_calibrations')
    op.drop_index('ix_ag054_board_calibrations_evaluation_id',table_name='ag054_board_calibrations')
    op.drop_table('ag054_board_calibrations')
