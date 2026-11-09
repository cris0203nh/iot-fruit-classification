"""AG-038: one-to-one evidence metadata for canonical Review events.

Revision ID: b38c99a10246
Revises: c7e41a03b037
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b38c99a10246'
down_revision: Union[str, Sequence[str], None] = 'c7e41a03b037'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_table(
        'review_decision_evidence',
        sa.Column('review_id', sa.Integer(), sa.ForeignKey('reviews.id'), primary_key=True),
        sa.Column('evaluation_id', sa.Integer(), sa.ForeignKey('evaluations.id'), nullable=False),
        sa.Column('image_id', sa.Integer(), sa.ForeignKey('images.id'), nullable=False),
        sa.Column('image_sha256', sa.String(64), nullable=False),
        sa.Column('action', sa.String(24), nullable=False),
        sa.Column('request_id', sa.String(36), nullable=False),
        sa.Column('payload_sha256', sa.String(64), nullable=False),
        sa.UniqueConstraint('evaluation_id', 'request_id', name='uq_ag038_evaluation_request'),
    )
    op.create_index('ix_ag038_decision_evaluation', 'review_decision_evidence', ['evaluation_id'])


def downgrade():
    op.drop_index('ix_ag038_decision_evaluation', table_name='review_decision_evidence')
    op.drop_table('review_decision_evidence')
