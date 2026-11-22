"""Corrige deriva Image/Alembic: clave nullable e idempotencia ya usadas por la API."""
from alembic import op
import sqlalchemy as sa

revision = 'c015imagekey'
down_revision = 'c014onboarding'
branch_labels = None
depends_on = None
INDEX = 'uq_image_evaluation_idempotency'


def upgrade():
    bind = op.get_bind()
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql('BEGIN IMMEDIATE')
    inspector = sa.inspect(bind)
    if 'idempotency_key' not in {column['name'] for column in inspector.get_columns('images')}:
        op.add_column('images', sa.Column('idempotency_key', sa.String(64), nullable=True))
    existing = inspector.get_indexes('images') + inspector.get_unique_constraints('images')
    if not any(item.get('column_names') == ['evaluation_id', 'idempotency_key']
               and (item.get('unique') or item in inspector.get_unique_constraints('images')) for item in existing):
        # NULL permite conservar fotografías históricas sin fabricar claves ni duplicar datos.
        op.create_index(INDEX, 'images', ['evaluation_id', 'idempotency_key'], unique=True)


def downgrade():
    bind = op.get_bind()
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql('BEGIN IMMEDIATE')
    if bind.exec_driver_sql('SELECT count(*) FROM images WHERE idempotency_key IS NOT NULL').scalar():
        raise RuntimeError('No eliminar claves de idempotencia registradas; restaurar respaldo autorizado.')
    if any(item['name'] == INDEX for item in sa.inspect(bind).get_indexes('images')):
        op.drop_index(INDEX, table_name='images')
    # No reconstruye tablas ni elimina fotografías; SQLite >= 3.35 soporta DROP COLUMN.
    bind.exec_driver_sql('ALTER TABLE images DROP COLUMN idempotency_key')
