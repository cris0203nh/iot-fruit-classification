"""Rutas de evidencia vinculadas a empresa/evaluación; compatibilidad histórica."""
from pathlib import Path, PurePosixPath

from fastapi import HTTPException


def evidence_relative(image) -> PurePosixPath:
    value = image.relative_path
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise HTTPException(409, 'Referencia de evidencia inválida.')
    path = PurePosixPath(value)
    parts = path.parts
    if path.is_absolute() or '..' in parts or not parts or parts[0] != 'images' or value != path.as_posix():
        raise HTTPException(409, 'Ruta de evidencia insegura.')
    if len(parts) > 1 and parts[1] == 'organizations':
        valid = len(parts) == 5 and parts[2] == str(image.organization_id) and parts[3] == f'E-{image.evaluation_id:06d}'
    elif len(parts) > 1 and parts[1].startswith('E-'):
        valid = len(parts) == 3 and parts[1] == f'E-{image.evaluation_id:06d}'
    else:
        # Solo la organización inicial posee referencias anteriores al aislamiento.
        valid = image.organization_id == 1 and len(parts) >= 2
    if not valid:
        raise HTTPException(409, 'La evidencia no pertenece a esta empresa y evaluación.')
    return path


def confined_path(root: Path, relative: PurePosixPath) -> Path:
    root = root.resolve(strict=True)
    target = root
    for part in relative.parts:
        target = target / part
        if target.is_symlink() or (hasattr(target, 'is_junction') and target.is_junction()):
            raise HTTPException(409, 'El almacenamiento contiene un enlace no permitido.')
    if not target.resolve().is_relative_to(root):
        raise HTTPException(409, 'Ruta fuera del almacenamiento autorizado.')
    return target


def evidence_path(image, root: Path, *, missing_status=409) -> Path:
    try:
        target = confined_path(root, evidence_relative(image))
        if not target.is_file():
            raise HTTPException(missing_status, 'Evidencia no disponible: el archivo falta.')
        if target.stat().st_size != image.size_bytes:
            raise HTTPException(409, 'La evidencia no coincide con el tamaño registrado.')
        return target
    except (OSError, ValueError, RuntimeError):
        raise HTTPException(409, 'Almacenamiento de evidencia no disponible.') from None


def capture_folder(root: Path, organization_id: int, evaluation_id: int) -> Path:
    relative = PurePosixPath(f'images/organizations/{organization_id}/E-{evaluation_id:06d}')
    target = confined_path(root, relative)
    target.mkdir(parents=True, exist_ok=True)
    return confined_path(root, relative)


def review_folder(root: Path, organization_id: int, *, create=False) -> Path:
    # Los archivos previos pertenecen a la organización inicial: no moverlos.
    if organization_id != 1:
        root = confined_path(root, PurePosixPath(f'organizations/{organization_id}'))
        if create:
            root.mkdir(parents=True, exist_ok=True)
    for child in ('reviews', 'registered_samples'):
        if root.exists():
            confined_path(root, PurePosixPath(child))
    return root
