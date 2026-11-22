"""Un intento de notificación por solicitud nueva; sin backfill ni cola."""
from alembic import op
import sqlalchemy as sa

revision = 'c013ownernotice'
down_revision = 'c012initialadmin'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql('BEGIN IMMEDIATE')
    op.create_table('commercial_application_notifications',
        sa.Column('application_id', sa.String(36), sa.ForeignKey('commercial_applications.id'), primary_key=True),
        sa.Column('status', sa.String(10), nullable=False),
        sa.Column('attempted_at', sa.DateTime), sa.Column('completed_at', sa.DateTime),
        sa.Column('error_code', sa.String(30)),
        sa.CheckConstraint("status IN ('pending','sending','sent','failed','disabled')", name='ck_application_notification_status'))


def downgrade():
    bind = op.get_bind()
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql('BEGIN IMMEDIATE')
    if bind.exec_driver_sql('SELECT count(*) FROM commercial_application_notifications').scalar():
        raise RuntimeError('Conservar el registro de intentos SMTP; restaurar respaldo para revertir sin duplicar avisos.')
    op.drop_table('commercial_application_notifications')
