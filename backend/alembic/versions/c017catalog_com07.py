"""Catalogo DEMO: metadatos aditivos; no cambia snapshots ni fechas historicas."""
from alembic import op
import sqlalchemy as sa

revision = 'c017catalog'
down_revision = 'a016sessions'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('commercial_plans') as batch:
        batch.add_column(sa.Column('display_order', sa.Integer(), server_default='0', nullable=False))
        batch.add_column(sa.Column('is_published', sa.Boolean(), server_default=sa.true(), nullable=False))
        batch.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('published_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('created_by', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('creation_key', sa.String(80), nullable=True))
        batch.add_column(sa.Column('creation_payload_hash', sa.String(64), nullable=True))
        batch.add_column(sa.Column('change_note', sa.String(500), server_default='', nullable=False))
        batch.create_foreign_key('fk_plan_creator', 'users', ['created_by'], ['id'])
        batch.create_unique_constraint('uq_plan_creation_key', ['creation_key'])


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text('SELECT 1 FROM commercial_plans WHERE created_at IS NOT NULL LIMIT 1')).first():
        raise RuntimeError('Hay versiones auditadas: restaura un respaldo consistente para revertir sin perder trazabilidad.')
    with op.batch_alter_table('commercial_plans') as batch:
        batch.drop_constraint('fk_plan_creator', type_='foreignkey')
        batch.drop_constraint('uq_plan_creation_key', type_='unique')
        for name in ('display_order', 'is_published', 'created_at', 'published_at', 'created_by', 'creation_key', 'creation_payload_hash', 'change_note'):
            batch.drop_column(name)
