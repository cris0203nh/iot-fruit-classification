"""SaaS-07: estaciones y dispositivos; históricos sin credenciales automáticas."""
from alembic import op
import sqlalchemy as sa

revision = 's007iot'
down_revision = 's006identity'
branch_labels = None
depends_on = None


def begin():
    bind = op.get_bind()
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql('BEGIN IMMEDIATE')
    if bind.exec_driver_sql('PRAGMA foreign_key_check').fetchall():
        raise RuntimeError('Integridad referencial incorrecta; migración detenida.')
    return bind


def upgrade():
    bind = begin()
    op.create_table('iot_stations',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('organization_id', sa.Integer, sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('code', sa.String(64), nullable=False),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('is_active', sa.Boolean, nullable=False),
        sa.UniqueConstraint('organization_id', 'id', name='uq_iot_stations_org_pk'),
        sa.UniqueConstraint('organization_id', 'code', name='uq_iot_station_code'))
    op.create_table('iot_devices',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('organization_id', sa.Integer, sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('station_id', sa.Integer, sa.ForeignKey('iot_stations.id'), nullable=False),
        sa.Column('device_id', sa.String(64), nullable=False),
        sa.Column('is_active', sa.Boolean, nullable=False),
        sa.Column('credential_hash', sa.String(64), nullable=True, unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('organization_id', 'id', name='uq_iot_devices_org_pk'),
        sa.UniqueConstraint('organization_id', 'device_id', name='uq_iot_device_code'),
        sa.ForeignKeyConstraint(['organization_id', 'station_id'],
            ['iot_stations.organization_id', 'iot_stations.id'], name='fk_iot_devices_org_station_id'))
    op.create_index('ix_iot_devices_station_id', 'iot_devices', ['station_id'])
    op.create_index('ix_iot_devices_org_station_id', 'iot_devices', ['organization_id', 'station_id'])
    # Identificadores históricos intactos: identidad administrativa inactiva,
    # sin secreto, hasta que su administrador la aprovisione explícitamente.
    bind.exec_driver_sql("""INSERT INTO iot_stations(organization_id,code,name,is_active)
        SELECT DISTINCT organization_id,'historical','Estación histórica',1 FROM measurements""")
    bind.exec_driver_sql("""INSERT INTO iot_devices(organization_id,station_id,device_id,is_active,credential_hash,created_at)
        SELECT DISTINCT m.organization_id,s.id,m.device_id,0,NULL,CURRENT_TIMESTAMP FROM measurements m
        JOIN iot_stations s ON s.organization_id=m.organization_id AND s.code='historical'""")
    with op.batch_alter_table('measurements', recreate='always') as batch:
        batch.create_foreign_key('fk_measurements_device', 'iot_devices',
            ['organization_id', 'device_id'], ['organization_id', 'device_id'])
        batch.create_index('ix_measurements_org_received', ['organization_id', 'id'])
    if bind.exec_driver_sql('PRAGMA foreign_key_check').fetchall():
        raise RuntimeError('La migración IoT no supera la integridad referencial.')


def downgrade():
    bind = begin()
    if bind.exec_driver_sql('SELECT 1 FROM iot_devices WHERE credential_hash IS NOT NULL OR is_active=1 LIMIT 1').first():
        raise RuntimeError('Reversión bloqueada: existen dispositivos aprovisionados.')
    if bind.exec_driver_sql("SELECT 1 FROM iot_stations WHERE code!='historical' OR name!='Estación histórica' OR is_active!=1 LIMIT 1").first():
        raise RuntimeError('Reversión bloqueada: existen estaciones modificadas.')
    with op.batch_alter_table('measurements', recreate='always') as batch:
        batch.drop_constraint('fk_measurements_device', type_='foreignkey')
        batch.drop_index('ix_measurements_org_received')
    op.drop_table('iot_devices')
    op.drop_table('iot_stations')
