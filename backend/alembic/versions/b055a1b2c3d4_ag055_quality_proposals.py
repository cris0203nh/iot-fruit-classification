"""AG-055 I01: propuestas experimentales append-only, nunca decisiones.

Revision ID: b055a1b2c3d4
Revises: a054d3e4f506
"""
from alembic import op
import sqlalchemy as sa

revision = 'b055a1b2c3d4'
down_revision = 'a054d3e4f506'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ag055_quality_predictions',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('evaluation_id', sa.Integer, sa.ForeignKey('evaluations.id'), nullable=False),
        sa.Column('product', sa.String(20), nullable=False),
        sa.Column('source_fingerprint', sa.String(64), nullable=False),
        sa.Column('model_sha256', sa.String(64), nullable=False),
        sa.Column('model_version', sa.String(100), nullable=False),
        sa.Column('status', sa.String(40), nullable=False),
        sa.Column('reason', sa.String(100), nullable=False),
        sa.Column('proposed_grade', sa.String(2), nullable=True),
        sa.Column('details_json', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('evaluation_id','source_fingerprint','model_sha256',
                            name='uq_ag055_evaluation_source_model'),
    )
    op.create_index('ix_ag055_quality_predictions_evaluation_id',
                    'ag055_quality_predictions',['evaluation_id'])


def downgrade():
    op.drop_index('ix_ag055_quality_predictions_evaluation_id',table_name='ag055_quality_predictions')
    op.drop_table('ag055_quality_predictions')
