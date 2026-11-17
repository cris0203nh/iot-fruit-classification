
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import uuid
import zipfile

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from ..database import DATA_DIR, engine
from contextlib import closing

DB_PATH = DATA_DIR / "agroscan.db"
IMAGES_DIR = DATA_DIR / "images"
BACKUP_DIR = DATA_DIR / "backups"

BACKUP_VERSION = 1
MAX_ENTRIES = 100_000
MAX_UNCOMPRESSED_BYTES = 10 * 1024 * 1024 * 1024


class BackupError(Exception):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def safe_relative_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)

    if (
        not normalized
        or path.is_absolute()
        or ".." in path.parts
        or ":" in normalized
        or not normalized.startswith("images/")
    ):
        raise BackupError("Ruta de imagen no permitida.")

    return path.as_posix()


def validate_database(path: Path) -> dict:
    if not path.is_file():
        raise BackupError("No existe la base de datos.")

    connection = sqlite3.connect(str(path))

    try:
        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if integrity != "ok":
            raise BackupError(
                f"Integridad SQLite incorrecta: {integrity}"
            )

        foreign_errors = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        if foreign_errors:
            raise BackupError(
                "La base de datos contiene relaciones inconsistentes."
            )

        rows = connection.execute(
            "SELECT id, relative_path FROM images"
        ).fetchall()

        return {
            "evaluationImageCount": len(rows),
            "imagePaths": [
                safe_relative_path(row[1])
                for row in rows
            ],
        }

    finally:
        connection.close()


def create_backup() -> dict:
    if not DB_PATH.is_file():
        raise BackupError("No se encuentra agroscan.db.")

    if not IMAGES_DIR.is_dir():
        raise BackupError("No se encuentra el directorio de imágenes.")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    backup_id = uuid.uuid4().hex
    filename = f"agroscan-backup-{backup_id}.zip"

    with tempfile.TemporaryDirectory(
        prefix="agroscan-backup-",
        dir=BACKUP_DIR,
    ) as temporary:

        temporary_dir = Path(temporary)
        database_copy = temporary_dir / "agroscan.db"

        # Copia consistente de SQLite, incluso si utiliza WAL.
        with closing(sqlite3.connect(str(DB_PATH))) as source:
            with closing(
                sqlite3.connect(str(database_copy))
            ) as destination:
                source.backup(destination)

        database_info = validate_database(database_copy)

        image_files = sorted(
            path for path in IMAGES_DIR.rglob("*")
            if path.is_file()
            and not path.name.endswith(".tmp")
            and not path.is_symlink()
        )

        included = {
            path.relative_to(DATA_DIR).as_posix()
            for path in image_files
        }

        for relative_path in database_info["imagePaths"]:
            if relative_path not in included:
                raise BackupError(
                    f"Falta una imagen asociada: {relative_path}"
                )

        manifest = {
            "version": BACKUP_VERSION,
            "backupId": backup_id,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "database": {
                "path": "database/agroscan.db",
                "sha256": sha256_file(database_copy),
            },
            "images": [
                {
                    "path": path.relative_to(DATA_DIR).as_posix(),
                    "sha256": sha256_file(path),
                    "size": path.stat().st_size,
                }
                for path in image_files
            ],
            "evaluationImageCount": database_info[
                "evaluationImageCount"
            ],
        }

        final_path = BACKUP_DIR / filename
        temporary_zip = BACKUP_DIR / f".{filename}.tmp"

        try:
            with zipfile.ZipFile(
                temporary_zip,
                "w",
                compression=zipfile.ZIP_DEFLATED,
            ) as archive:

                archive.write(
                    database_copy,
                    "database/agroscan.db",
                )

                for image in image_files:
                    archive.write(
                        image,
                        "payload/"
                        + image.relative_to(DATA_DIR).as_posix(),
                    )

                archive.writestr(
                    "manifest.json",
                    json.dumps(
                        manifest,
                        ensure_ascii=False,
                        indent=2,
                    ),
                )

            # Publicación atómica del respaldo.
            os.replace(temporary_zip, final_path)

        finally:
            if temporary_zip.exists():
                temporary_zip.unlink()

    return {
        "backupId": backup_id,
        "filename": filename,
        "path": str(final_path),
        "imageFiles": len(image_files),
        "evaluationImages": manifest["evaluationImageCount"],
        "sizeBytes": final_path.stat().st_size,
        "createdAt": manifest["createdAt"],
    }


def prepare_restore(archive_path: Path, staging: Path) -> dict:
    if not archive_path.is_file():
        raise BackupError("El respaldo solicitado no existe.")

    if not zipfile.is_zipfile(archive_path):
        raise BackupError("El archivo no es un ZIP válido.")

    staging.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive_path, "r") as archive:
        entries = archive.infolist()

        if len(entries) > MAX_ENTRIES:
            raise BackupError("El respaldo contiene demasiados archivos.")

        total_size = sum(item.file_size for item in entries)

        if total_size > MAX_UNCOMPRESSED_BYTES:
            raise BackupError("El respaldo supera el tamaño permitido.")

        names = [item.filename for item in entries]

        if len(names) != len(set(names)):
            raise BackupError("El ZIP contiene rutas duplicadas.")

        if "manifest.json" not in names:
            raise BackupError("Falta el manifiesto del respaldo.")

        if "database/agroscan.db" not in names:
            raise BackupError("Falta la base de datos del respaldo.")

        for item in entries:
            name = item.filename

            if item.is_dir():
                continue

            if name.startswith("/"):
                raise BackupError("Ruta absoluta no permitida.")

            if ".." in PurePosixPath(name).parts:
                raise BackupError("Ruta insegura en el ZIP.")

            if item.flag_bits & 0x1:
                raise BackupError("No se admiten archivos cifrados.")

        manifest = json.loads(
            archive.read("manifest.json")
        )

        if manifest.get("version") != BACKUP_VERSION:
            raise BackupError("Versión de respaldo incompatible.")

        database_path = staging / "agroscan.db"

        database_path.write_bytes(
            archive.read("database/agroscan.db")
        )

        if sha256_file(database_path) != manifest["database"]["sha256"]:
            raise BackupError("La base de datos no supera el SHA-256.")

        restored_images = staging / "images"
        restored_images.mkdir()

        expected = {
            "manifest.json",
            "database/agroscan.db",
        }

        for image in manifest["images"]:
            relative = safe_relative_path(image["path"])

            archive_name = "payload/" + relative
            expected.add(archive_name)

            if archive_name not in names:
                raise BackupError(
                    f"Falta una imagen: {relative}"
                )

            destination = staging / relative

            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            content = archive.read(archive_name)

            if hashlib.sha256(content).hexdigest() != image["sha256"]:
                raise BackupError(
                    f"Imagen alterada: {relative}"
                )

            if len(content) != image["size"]:
                raise BackupError(
                    f"Tamaño incorrecto: {relative}"
                )

            destination.write_bytes(content)

        if set(names) != expected:
            raise BackupError(
                "El respaldo contiene archivos no declarados."
            )

    database_info = validate_database(database_path)

    for relative in database_info["imagePaths"]:
        restored_path = staging / relative

        if not restored_path.is_file():
            raise BackupError(
                f"La evaluación tiene una imagen ausente: {relative}"
            )

    if (
        database_info["evaluationImageCount"]
        != manifest["evaluationImageCount"]
    ):
        raise BackupError(
            "La cantidad de imágenes asociadas no coincide."
        )

    return {
        "database": str(database_path),
        "images": str(restored_images),
        "evaluationImageCount": database_info[
            "evaluationImageCount"
        ],
        "verified": True,
    }


def _checkpoint_before_replace() -> bool:
    """Retira WAL/SHM mediante SQLite; nunca elimina un journal a mano."""
    if not DB_PATH.exists():
        return False
    try:
        with closing(sqlite3.connect(str(DB_PATH), timeout=5)) as connection:
            was_wal = connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
            if was_wal:
                busy, _, _ = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                if busy:
                    raise BackupError("SQLite ocupado; cierre las conexiones antes de restaurar.")
                # También rechaza conexiones WAL externas todavía abiertas.
                mode = connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
                if mode != "delete":
                    raise BackupError("No fue posible cerrar el WAL antes de restaurar.")
            return was_wal
    except sqlite3.OperationalError as exc:
        raise BackupError("SQLite ocupado; no se sustituyó la base de datos.") from exc


def _enable_wal_after_replace():
    with closing(sqlite3.connect(str(DB_PATH))) as connection:
        if connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] != "wal":
            raise BackupError("No fue posible recuperar el modo WAL.")


def restore_backup(archive_path: Path) -> dict:
    """
    Restauración con copia de seguridad previa para permitir rollback.
    El router debe ejecutar esta operación dentro de suspend_capture().
    """

    with tempfile.TemporaryDirectory(
        prefix="agroscan-restore-",
        dir=DATA_DIR,
    ) as temporary:

        staging = Path(temporary)

        prepared = prepare_restore(
            archive_path,
            staging,
        )

        staged_database = Path(prepared["database"])
        staged_images = Path(prepared["images"])

        rollback = staging / "rollback"
        rollback.mkdir()

        old_database = rollback / "agroscan.db"
        old_images = rollback / "images"

        database_moved = False
        images_moved = False
        new_database_installed = False
        new_images_installed = False

        # Evita mantener conexiones del pool abiertas al sustituir SQLite.
        engine.dispose()
        was_wal = _checkpoint_before_replace()

        try:
            if DB_PATH.exists():
                shutil.copy2(DB_PATH, old_database)
                os.replace(DB_PATH, rollback / "previous.db")
                database_moved = True

            if IMAGES_DIR.exists():
                os.replace(IMAGES_DIR, old_images)
                images_moved = True

            os.replace(staged_database, DB_PATH)
            new_database_installed = True

            os.replace(staged_images, IMAGES_DIR)
            new_images_installed = True

            if was_wal:
                _enable_wal_after_replace()

            final_check = validate_database(DB_PATH)

            for relative in final_check["imagePaths"]:
                if not (DATA_DIR / relative).is_file():
                    raise BackupError(
                        f"Falta imagen tras restaurar: {relative}"
                    )

            return {
                "restored": True,
                "verified": True,
                "evaluationImages": final_check[
                    "evaluationImageCount"
                ],
            }

        except Exception:
            # Revertir la instalación si alguna operación falla.
            if new_images_installed and IMAGES_DIR.exists():
                shutil.rmtree(IMAGES_DIR)

            if images_moved and old_images.exists():
                os.replace(old_images, IMAGES_DIR)

            if new_database_installed and DB_PATH.exists():
                DB_PATH.unlink()

            previous_database = rollback / "previous.db"

            if database_moved and previous_database.exists():
                os.replace(previous_database, DB_PATH)

            if was_wal and DB_PATH.exists():
                _enable_wal_after_replace()

            engine.dispose()
            raise
