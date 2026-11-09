"""AG-037: immutable snapshots of YOLOE detector decisions.

Revision ID: c7e41a03b037
Revises: 641b11d4880b
"""
from alembic import op
import sqlalchemy as sa

revision = 'c7e41a03b037'
down_revision = '641b11d4880b'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'vision_assessments',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('evaluation_id', sa.Integer, sa.ForeignKey('evaluations.id'), nullable=False),
        sa.Column('image_id', sa.Integer, sa.ForeignKey('images.id'), nullable=False),
        sa.Column('image_sha256', sa.String(64), nullable=False),
        sa.Column('model_version', sa.String(100), nullable=False),
        sa.Column('rules_version', sa.String(64), nullable=False),
        sa.Column('inference_size', sa.Integer, nullable=False),
        sa.Column('inference_confidence', sa.Float, nullable=False),
        sa.Column('acceptance_threshold', sa.Float, nullable=False),
        sa.Column('outcome', sa.String(32), nullable=False),
        sa.Column('reason', sa.String(64), nullable=False),
        sa.Column('confidence', sa.Float, nullable=True),
        sa.Column('candidate_count', sa.Integer, nullable=False),
        sa.Column('detections_json', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('image_id', 'image_sha256','rules_version','model_version',
                            name='uq_vision_image_model_rules'),
    )
    op.create_index('ix_vision_assessments_evaluation_id','vision_assessments',['evaluation_id'])
    op.create_index('ix_vision_assessments_image_id','vision_assessments',['image_id'])


def downgrade():
    op.drop_index('ix_vision_assessments_image_id',table_name='vision_assessments')
    op.drop_index('ix_vision_assessments_evaluation_id',table_name='vision_assessments')
    op.drop_table('vision_assessments')
