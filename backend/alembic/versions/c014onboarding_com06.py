"""Enlace explícito de primera contratación; sin backfill de suscripciones legacy."""
from alembic import op
import sqlalchemy as sa

revision = 'c014onboarding'
down_revision = 'c013ownernotice'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql('BEGIN IMMEDIATE')
    op.create_index('uq_initial_invitation_trace','commercial_application_invitations',
                    ['application_id','organization_id','invitation_id'],unique=True)
    op.create_table('commercial_onboarding_orders',
        sa.Column('order_id',sa.String(36),primary_key=True),
        sa.Column('application_id',sa.String(36),nullable=False),
        sa.Column('invitation_id',sa.Integer,nullable=False),
        sa.Column('subscription_id',sa.Integer),
        sa.Column('accepted_updated_plan',sa.Boolean,nullable=False),
        sa.Column('organization_id',sa.Integer,sa.ForeignKey('organizations.id'),nullable=False),
        sa.UniqueConstraint('organization_id','order_id',name='uq_commercial_onboarding_orders_org_pk'),
        sa.ForeignKeyConstraint(['organization_id','order_id'],['commercial_orders.organization_id','commercial_orders.id'],name='fk_commercial_onboarding_orders_org_order_id'),
        sa.ForeignKeyConstraint(['organization_id','subscription_id'],['commercial_subscriptions.organization_id','commercial_subscriptions.id'],name='fk_commercial_onboarding_orders_org_subscription_id'),
        sa.ForeignKeyConstraint(['application_id','organization_id','invitation_id'],
            ['commercial_application_invitations.application_id','commercial_application_invitations.organization_id','commercial_application_invitations.invitation_id']))
    op.create_index('ix_commercial_onboarding_orders_org_subscription_id','commercial_onboarding_orders',['organization_id','subscription_id'])
    op.create_index('uq_onboarding_completed','commercial_onboarding_orders',['application_id'],unique=True,sqlite_where=sa.text('subscription_id IS NOT NULL'))


def downgrade():
    bind = op.get_bind()
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql('BEGIN IMMEDIATE')
    if bind.exec_driver_sql('SELECT count(*) FROM commercial_onboarding_orders').scalar():
        raise RuntimeError('Conservar trazabilidad de contratación; revertir mediante respaldo autorizado.')
    op.drop_table('commercial_onboarding_orders')
    op.drop_index('uq_initial_invitation_trace',table_name='commercial_application_invitations')
