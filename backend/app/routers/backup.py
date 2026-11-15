
from pathlib import Path
import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ..dependencies import require_admin
from ..services.backup_service import (
    BACKUP_DIR,
    BackupError,
    create_backup,
    restore_backup,
)
from ..services.capture_control import suspend_capture


router = APIRouter(
    prefix="/api/admin/backups",
    tags=["respaldos"],
    dependencies=[Depends(require_admin)],
)

MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024


@router.post("")
def create_backup_endpoint():
    """
    Crea un respaldo de la base de datos y las imágenes.
    Solo administradores.
    """
    try:
        with suspend_capture():
            result = create_backup()

        return {
            "success": True,
            "message": "Respaldo creado y verificado.",
            "backup": {
                key: value
                for key, value in result.items()
                if key != "path"
            },
        }

    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except BackupError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="No fue posible completar el respaldo.",
        ) from exc


@router.post("/restore")
async def restore_backup_endpoint(
    file: UploadFile = File(...),
):
    """
    Restaura un respaldo ZIP.
    Suspende las capturas durante toda la restauración.
    Solo administradores.
    """
    if not file.filename or Path(file.filename).suffix.lower() != ".zip":
        raise HTTPException(
            status_code=422,
            detail="Debes proporcionar un archivo ZIP de respaldo.",
        )

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            prefix="restore-upload-",
            suffix=".zip",
            dir=BACKUP_DIR,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            total = 0

            while True:
                chunk = await file.read(1024 * 1024)

                if not chunk:
                    break

                total += len(chunk)

                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="El archivo supera el límite de 2 GB.",
                    )

                temporary.write(chunk)

        if total == 0:
            raise HTTPException(
                status_code=422,
                detail="El archivo de respaldo está vacío.",
            )

        try:
            with suspend_capture():
                result = restore_backup(temporary_path)

        except RuntimeError as exc:
            raise HTTPException(
                status_code=409,
                detail=str(exc),
            ) from exc

        except BackupError as exc:
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            ) from exc

        return {
            "success": True,
            "message": "Restauración completada y verificada.",
            "restoration": result,
        }

    finally:
        await file.close()

        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
