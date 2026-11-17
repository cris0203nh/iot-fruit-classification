"""SaaS-03: organizaciones y pertenencia de recursos, SQLite.

Revision ID: s003organizations
Revises: b055a1b2c3d4
"""
from alembic import op
import sqlalchemy as sa

revision = 's003organizations'
down_revision = 'b055a1b2c3d4'
branch_labels = None
depends_on = None

# Instantánea de la especificación: la migración no importa modelos futuros.
TENANT_LINKS = {'lots': {},
 'measurements': {},
 'pieces': {'lot_id': 'lots'},
 'evaluations': {'lot_id': 'lots',
                 'piece_ref_id': 'pieces',
                 'weight_pre_measurement_id': 'measurements',
                 'weight_post_measurement_id': 'measurements'},
 'images': {'evaluation_id': 'evaluations'},
 'reviews': {'evaluation_id': 'evaluations'},
 'vision_assessments': {'evaluation_id': 'evaluations', 'image_id': 'images'},
 'review_decision_evidence': {'review_id': 'reviews',
                              'evaluation_id': 'evaluations',
                              'image_id': 'images'},
 'vision_prechecks': {'registered_lot_id': 'lots', 'evaluation_id': 'evaluations'},
 'fruit_geometries': {'evaluation_id': 'evaluations', 'image_id': 'images'},
 'ag054_planar_calibrations': {'evaluation_id': 'evaluations',
                               'image_id': 'images',
                               'geometry_id': 'fruit_geometries'},
 'ag054_board_calibrations': {'evaluation_id': 'evaluations',
                              'image_id': 'images',
                              'geometry_id': 'fruit_geometries'},
 'ag054_dimensional_comparisons': {'board_calibration_id': 'ag054_board_calibrations'},
 'ag055_quality_predictions': {'evaluation_id': 'evaluations'}}
RESOURCE_LINKS = {'evaluations': [('pieces', ('lot_id', 'piece_ref_id'), ('lot_id', 'id'))],
 'vision_prechecks': [('evaluations', ('registered_lot_id', 'evaluation_id'), ('lot_id', 'id'))],
 'vision_assessments': [('images', ('evaluation_id', 'image_id'), ('evaluation_id', 'id'))],
 'review_decision_evidence': [('images', ('evaluation_id', 'image_id'), ('evaluation_id', 'id')),
                              ('reviews', ('evaluation_id', 'review_id'), ('evaluation_id', 'id'))],
 'fruit_geometries': [('images', ('evaluation_id', 'image_id'), ('evaluation_id', 'id'))],
 'ag054_planar_calibrations': [('images', ('evaluation_id', 'image_id'), ('evaluation_id', 'id')),
                               ('fruit_geometries',
                                ('evaluation_id', 'image_id', 'geometry_id'),
                                ('evaluation_id', 'image_id', 'id'))],
 'ag054_board_calibrations': [('images', ('evaluation_id', 'image_id'), ('evaluation_id', 'id')),
                              ('fruit_geometries',
                               ('evaluation_id', 'image_id', 'geometry_id'),
                               ('evaluation_id', 'image_id', 'id'))]}
PARENT_KEYS = {'pieces': ('lot_id', 'id'),
 'evaluations': ('lot_id', 'id'),
 'images': ('evaluation_id', 'id'),
 'reviews': ('evaluation_id', 'id'),
 'fruit_geometries': ('evaluation_id', 'image_id', 'id')}


def _begin():
    bind = op.get_bind()
    # La reconstrucción de índices no depende del directorio TEMP del host.
    bind.exec_driver_sql('PRAGMA temp_store=MEMORY')
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql('BEGIN IMMEDIATE')
    return bind


def upgrade():
    bind = _begin()
    if bind.exec_driver_sql('PRAGMA foreign_key_check').fetchall():
        raise RuntimeError('Corrige la integridad referencial antes de migrar.')
    if bind.exec_driver_sql('SELECT lower(code) FROM lots GROUP BY lower(code) HAVING count(*) > 1').first():
        raise RuntimeError('Hay códigos de lote incompatibles con la unicidad por organización.')
    # Verificar relaciones indirectas antes de cambiar el esquema.
    for table, links in RESOURCE_LINKS.items():
        for parent, columns, targets in links:
            join = ' AND '.join(f'c."{c}" = p."{p}"' for c, p in zip(columns, targets))
            not_null = ' AND '.join(f'c."{c}" IS NOT NULL' for c in columns)
            sql = f'SELECT 1 FROM "{table}" c WHERE {not_null} AND NOT EXISTS (SELECT 1 FROM "{parent}" p WHERE {join}) LIMIT 1'
            if bind.exec_driver_sql(sql).first():
                raise RuntimeError(f'Relación indirecta inconsistente en {table}.')
    op.create_table('organizations',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('is_active', sa.Boolean, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    bind.exec_driver_sql("INSERT INTO organizations VALUES (1, 'AgroScan Inicial', 1, CURRENT_TIMESTAMP)")
    op.create_table('organization_memberships',
        sa.Column('organization_id', sa.Integer, sa.ForeignKey('organizations.id'), primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('role_id', sa.Integer, sa.ForeignKey('roles.id'), primary_key=True),
        sa.Column('is_active', sa.Boolean, nullable=False))
    op.create_index('ix_organization_memberships_user_id', 'organization_memberships', ['user_id'])
    op.create_index('ix_organization_memberships_role_id', 'organization_memberships', ['role_id'])
    bind.exec_driver_sql('INSERT INTO organization_memberships SELECT 1, user_id, role_id, 1 FROM user_roles')
    for name in TENANT_LINKS:
        op.add_column(name, sa.Column('organization_id', sa.Integer, nullable=True))
        bind.exec_driver_sql(f'UPDATE "{name}" SET organization_id=1')
    op.drop_index('ix_lots_code', table_name='lots')
    for name, links in TENANT_LINKS.items():
        pk = 'review_id' if name == 'review_decision_evidence' else 'token' if name == 'vision_prechecks' else 'id'
        with op.batch_alter_table(name, recreate='always') as batch:
            batch.alter_column('organization_id', existing_type=sa.Integer, nullable=False)
            batch.create_foreign_key(f'fk_{name}_organization_id', 'organizations', ['organization_id'], ['id'])
            batch.create_unique_constraint(f'uq_{name}_org_pk', ['organization_id', pk])
            if name in PARENT_KEYS:
                batch.create_unique_constraint(f'uq_{name}_org_resource', ['organization_id', *PARENT_KEYS[name]])
            if name == 'lots':
                batch.alter_column('code', existing_type=sa.String(32), type_=sa.String(32, collation='NOCASE'))
                batch.create_unique_constraint('uq_lots_organization_code', ['organization_id', 'code'])
            if name == 'measurements':
                batch.drop_constraint('uq_measurement_seq', type_='unique')
                batch.create_unique_constraint('uq_measurement_seq', ['organization_id', 'device_id', 'boot_id', 'seq'])
            for column, parent in links.items():
                batch.create_foreign_key(f'fk_{name}_org_{column}', parent,
                    ['organization_id', column], ['organization_id', 'id'])
                if column != pk:
                    batch.create_index(f'ix_{name}_org_{column}', ['organization_id', column])
            for number, (parent, columns, targets) in enumerate(RESOURCE_LINKS.get(name, ())):
                batch.create_foreign_key(f'fk_{name}_resource_{number}', parent,
                    ['organization_id', *columns], ['organization_id', *targets])
    if bind.exec_driver_sql('PRAGMA foreign_key_check').fetchall():
        raise RuntimeError('La migración no supera la integridad empresarial.')


def downgrade():
    bind = _begin()
    if bind.exec_driver_sql('PRAGMA foreign_key_check').fetchall():
        raise RuntimeError('Downgrade bloqueado: existen relaciones inconsistentes.')
    if bind.exec_driver_sql('SELECT count(*) FROM organizations').scalar() != 1 or bind.exec_driver_sql('SELECT id FROM organizations').scalar() != 1:
        raise RuntimeError('Downgrade bloqueado: existen organizaciones adicionales.')
    if bind.exec_driver_sql('SELECT user_id, role_id FROM organization_memberships EXCEPT SELECT user_id, role_id FROM user_roles').first() or bind.exec_driver_sql('SELECT user_id, role_id FROM user_roles EXCEPT SELECT user_id, role_id FROM organization_memberships').first() or bind.exec_driver_sql('SELECT 1 FROM organization_memberships WHERE is_active=0 LIMIT 1').first():
        raise RuntimeError('Downgrade bloqueado: cambiaron las membresías; no se perderán permisos silenciosamente.')
    for name, links in reversed(list(TENANT_LINKS.items())):
        pk = 'review_id' if name == 'review_decision_evidence' else 'token' if name == 'vision_prechecks' else 'id'
        with op.batch_alter_table(name, recreate='always') as batch:
            for number in range(len(RESOURCE_LINKS.get(name, ()))):
                batch.drop_constraint(f'fk_{name}_resource_{number}', type_='foreignkey')
            for column in links:
                batch.drop_constraint(f'fk_{name}_org_{column}', type_='foreignkey')
                if column != pk:
                    batch.drop_index(f'ix_{name}_org_{column}')
            if name in PARENT_KEYS:
                batch.drop_constraint(f'uq_{name}_org_resource', type_='unique')
            batch.drop_constraint(f'uq_{name}_org_pk', type_='unique')
            batch.drop_constraint(f'fk_{name}_organization_id', type_='foreignkey')
            if name == 'lots':
                batch.drop_constraint('uq_lots_organization_code', type_='unique')
                batch.alter_column('code', existing_type=sa.String(32, collation='NOCASE'), type_=sa.String(32))
            if name == 'measurements':
                batch.drop_constraint('uq_measurement_seq', type_='unique')
                batch.create_unique_constraint('uq_measurement_seq', ['device_id', 'boot_id', 'seq'])
            batch.drop_column('organization_id')
    op.create_index('ix_lots_code', 'lots', ['code'], unique=True)
    op.drop_table('organization_memberships')
    op.drop_table('organizations')
