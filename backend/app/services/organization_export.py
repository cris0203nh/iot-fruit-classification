"""Exportación lógica empresarial, sin páginas SQLite ni secretos de autenticación."""
import hashlib
import json
import tempfile
import zipfile
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import select

from ..database import Base
from ..models import Role, User
from ..organization_models import Organization, OrganizationMembership
from .evidence_storage import evidence_path

MAX_ROWS = 100_000
MAX_BYTES = 512 * 1024 * 1024
EXPORT_TABLES = ('lots', 'pieces', 'measurements', 'evaluations', 'images', 'reviews',
                 'vision_assessments', 'review_decision_evidence', 'vision_prechecks',
                 'fruit_geometries', 'ag054_planar_calibrations', 'ag054_board_calibrations',
                 'ag054_dimensional_comparisons', 'ag055_quality_predictions',
                 'iot_stations', 'iot_devices')


def organization_export(db, root):
    org = db.info.get('organization_id')
    if org is None:
        raise HTTPException(403, 'Se requiere empresa autorizada.')
    # Snapshot SQLite explícito; las fotografías registradas son inmutables.
    if not db.connection().connection.driver_connection.in_transaction:
        db.connection().exec_driver_sql('BEGIN')
    tables = {}
    for name in EXPORT_TABLES:
        table = Base.metadata.tables[name]
        columns = [c for c in table.c if c.name not in ('credential_hash', 'token')]
        rows = db.execute(select(*columns).where(table.c.organization_id == org).limit(MAX_ROWS + 1)).mappings().all()
        if len(rows) > MAX_ROWS:
            raise HTTPException(413, 'La exportación supera el límite de registros.')
        tables[name] = [dict(row) for row in rows]
    organization = db.get(Organization, org)
    tables['organizations'] = [{'id': org, 'name': organization.name, 'is_active': organization.is_active}]
    tables['memberships'] = [dict(row) for row in db.execute(select(
        OrganizationMembership.user_id, Role.name.label('role'), OrganizationMembership.is_active,
        User.username, User.full_name).join(Role, OrganizationMembership.role_id == Role.id)
        .join(User, User.id == OrganizationMembership.user_id).where(
            OrganizationMembership.organization_id == org)).mappings()]
    data = json.dumps({'format': 'agroscan-organization-export-v1', 'organizationId': org,
                       'tables': tables}, default=lambda value: value.isoformat(), ensure_ascii=False).encode()
    if len(data) > 64 * 1024 * 1024:
        raise HTTPException(413, 'Los datos de la exportación superan el límite.')
    images = [SimpleNamespace(**row) for row in tables['images']]
    # Cerrar el snapshot antes de comprimir archivos inmutables: no retener
    # lectores SQLite que bloqueen escrituras en instalaciones sin WAL.
    db.rollback()
    output = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    try:
        hashes = [{'path': 'data.json', 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}]
        total, included = len(data), set()
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('data.json', data)
            for image in images:
                path = evidence_path(image, root)
                if not 0 < image.size_bytes <= 5 * 1024 * 1024:
                    raise HTTPException(409, 'Evidencia fuera de límites; exportación cancelada.')
                with path.open('rb') as source:
                    raw = source.read(5 * 1024 * 1024 + 1)
                if len(raw) != image.size_bytes:
                    raise HTTPException(409, 'Evidencia inconsistente; exportación cancelada.')
                relative = image.relative_path
                if relative in included:
                    continue
                total += len(raw)
                if total > MAX_BYTES:
                    raise HTTPException(413, 'La exportación supera 512 MiB.')
                included.add(relative)
                archive.writestr(relative, raw)
                hashes.append({'path': relative, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
            archive.writestr('manifest.json', json.dumps({'organizationId': org,
                'createdAt': datetime.now(timezone.utc).isoformat(), 'files': hashes}).encode())
        output.seek(0)
        return output
    except BaseException:
        output.close()
        raise
