"""Aislamiento ORM por solicitud y restricciones SQLite de pertenencia."""
from fastapi import HTTPException
from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Session, mapped_column, with_loader_criteria

# Relaciones a recursos empresariales. Los usuarios son identidades compartidas.
TENANT_LINKS = {
    'commercial_onboarding_orders': {'order_id': 'commercial_orders', 'subscription_id': 'commercial_subscriptions'},
    'commercial_subscriptions': {}, 'commercial_orders': {},
    'commercial_transactions': {'order_id': 'commercial_orders'},
    'iot_stations': {}, 'iot_devices': {'station_id': 'iot_stations'},
    'organization_invitations': {},
    'lots': {}, 'measurements': {},
    'pieces': {'lot_id': 'lots'},
    'evaluations': {'lot_id': 'lots', 'piece_ref_id': 'pieces',
                    'weight_pre_measurement_id': 'measurements', 'weight_post_measurement_id': 'measurements'},
    'images': {'evaluation_id': 'evaluations'},
    'reviews': {'evaluation_id': 'evaluations'},
    'vision_assessments': {'evaluation_id': 'evaluations', 'image_id': 'images'},
    'review_decision_evidence': {'review_id': 'reviews', 'evaluation_id': 'evaluations', 'image_id': 'images'},
    'vision_prechecks': {'registered_lot_id': 'lots', 'evaluation_id': 'evaluations'},
    'fruit_geometries': {'evaluation_id': 'evaluations', 'image_id': 'images'},
    'ag054_planar_calibrations': {'evaluation_id': 'evaluations', 'image_id': 'images', 'geometry_id': 'fruit_geometries'},
    'ag054_board_calibrations': {'evaluation_id': 'evaluations', 'image_id': 'images', 'geometry_id': 'fruit_geometries'},
    'ag054_dimensional_comparisons': {'board_calibration_id': 'ag054_board_calibrations'},
    'ag055_quality_predictions': {'evaluation_id': 'evaluations'},
}

# Además de la organización, estos enlaces deben compartir lote/evaluación/imagen.
RESOURCE_LINKS = {
    'evaluations': [('pieces', ('lot_id', 'piece_ref_id'), ('lot_id', 'id'))],
    'vision_prechecks': [('evaluations', ('registered_lot_id', 'evaluation_id'), ('lot_id', 'id'))],
    **{name: [('images', ('evaluation_id', 'image_id'), ('evaluation_id', 'id'))]
       for name in ('vision_assessments', 'review_decision_evidence', 'fruit_geometries',
                    'ag054_planar_calibrations', 'ag054_board_calibrations')},
}
RESOURCE_LINKS['review_decision_evidence'].append(('reviews', ('evaluation_id', 'review_id'), ('evaluation_id', 'id')))
for name in ('ag054_planar_calibrations', 'ag054_board_calibrations'):
    RESOURCE_LINKS[name].append(('fruit_geometries', ('evaluation_id', 'image_id', 'geometry_id'),
                               ('evaluation_id', 'image_id', 'id')))
PARENT_KEYS = {'pieces': ('lot_id', 'id'), 'evaluations': ('lot_id', 'id'),
               'images': ('evaluation_id', 'id'), 'reviews': ('evaluation_id', 'id'),
               'fruit_geometries': ('evaluation_id', 'image_id', 'id')}


class OrganizationScoped:
    organization_id: Mapped[int] = mapped_column(ForeignKey('organizations.id'), nullable=False)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        table = cls.__table__
        name = table.name
        pk = next(iter(table.primary_key.columns)).name
        table.append_constraint(UniqueConstraint('organization_id', pk, name=f'uq_{name}_org_pk'))
        if name in PARENT_KEYS:
            table.append_constraint(UniqueConstraint('organization_id', *PARENT_KEYS[name], name=f'uq_{name}_org_resource'))
        for column, parent in TENANT_LINKS[name].items():
            table.append_constraint(ForeignKeyConstraint(
                ['organization_id', column], [f'{parent}.organization_id', f'{parent}.id'],
                name=f'fk_{name}_org_{column}'))
            if column != pk:
                Index(f'ix_{name}_org_{column}', table.c.organization_id, table.c[column])
        for number, (parent, columns, targets) in enumerate(RESOURCE_LINKS.get(name, ())):
            table.append_constraint(ForeignKeyConstraint(
                ['organization_id', *columns], [f'{parent}.organization_id', *[f'{parent}.{c}' for c in targets]],
                name=f'fk_{name}_resource_{number}'))


@event.listens_for(Session, 'do_orm_execute')
def scope_organization_queries(state):
    organization_id = state.session.info.get('organization_id')
    if organization_id is None:
        # Sesiones CLI/migración no son solicitudes. get_db marca las solicitudes.
        if state.session.info.get('organization_required') and (
                not state.session.info.get('platform_authorized') or not state.is_select):
            for mapper in state.all_mappers:
                if issubclass(mapper.class_, OrganizationScoped):
                    raise HTTPException(403, 'Se requiere contexto empresarial autorizado.')
        return
    if state.is_select or state.is_update or state.is_delete:
        state.statement = state.statement.options(with_loader_criteria(
            OrganizationScoped, lambda cls: cls.organization_id == organization_id,
            include_aliases=True))


@event.listens_for(Session, 'before_flush')
def scope_organization_writes(session, flush_context, instances):
    organization_id = session.info.get('organization_id')
    for item in session.new.union(session.dirty).union(session.deleted):
        if not isinstance(item, OrganizationScoped):
            continue
        if organization_id is None:
            if session.info.get('organization_required'):
                raise HTTPException(403, 'Se requiere contexto empresarial autorizado.')
            continue
        if item in session.new and item.organization_id is None:
            item.organization_id = organization_id
        if item.organization_id != organization_id:
            raise HTTPException(403, 'El recurso no pertenece a la organización activa.')
