#!/usr/bin/env python3
"""Crear una copia PRIVADA e independiente para una demostracion web.

La base original se lee con SQLite backup, nunca se mueve ni se modifica.
La carpeta .agroscan_demo/ esta excluida del control de versiones.
"""
from __future__ import annotations
import argparse
import os
import shutil
import sqlite3
import sys
import uuid
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend" / "data"
PRIVATE = ROOT / ".agroscan_demo"
DEST = PRIVATE / "data"


def check() -> int:
    db = SOURCE / "agroscan.db"
    print(f"Fuente (SOLO LECTURA): {SOURCE}")
    print(f"Destino demo: {DEST}")
    print(f"SQLite fuente: {'ENCONTRADA' if db.is_file() else 'NO ENCONTRADA'}")
    images = SOURCE / "images"
    print(f"Fotografias: {'DISPONIBLES' if images.is_dir() else 'NO DISPONIBLES'}")
    print(f"Copia demo ya existe: {'SI (no se sobrescribira)' if DEST.exists() else 'NO'}")
    if not db.is_file() or DEST.exists() or DEST.is_symlink():
        return 1
    if images.is_symlink():
        print("BLOQUEADO: images es un enlace simbolico")
        return 1
    return 0


def create() -> int:
    if check():
        print("BLOQUEADO: comprueba la base original y que el destino aun no exista")
        return 1
    PRIVATE.mkdir(exist_ok=True)
    staging = PRIVATE / (".staging_" + uuid.uuid4().hex)
    staging.mkdir()
    try:
        with closing(sqlite3.connect(f"file:{(SOURCE / 'agroscan.db').as_posix()}?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(str(staging / "agroscan.db"))) as dst:
                src.backup(dst)
        with closing(sqlite3.connect(str(staging / "agroscan.db"))) as db:
            result = db.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise RuntimeError("Copia SQLite no supera integrity_check")
        images = SOURCE / "images"
        if images.is_dir():
            for path in images.rglob("*"):
                if path.is_symlink():
                    raise RuntimeError("No se copian enlaces simbolicos de imagenes")
            shutil.copytree(images, staging / "images", symlinks=False)
        else:
            (staging / "images").mkdir()
        # Los modelos permanecen en su directorio original; no se copian.
        os.rename(staging, DEST)
        print("COPIA AISLADA CREADA. No se modificaron SQLite, fotos ni modelos originales.")
        return 0
    except Exception as exc:
        shutil.rmtree(staging, ignore_errors=True)
        print(f"BLOQUEADO: {exc}", file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--create", action="store_true")
    args = parser.parse_args()
    return check() if args.check else create()


if __name__ == "__main__":
    sys.exit(main())
