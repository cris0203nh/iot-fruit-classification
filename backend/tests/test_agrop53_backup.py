
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile

from pathlib import Path
from unittest.mock import Mock, patch

from app.services import backup_service
from contextlib import closing


class AGROP53BackupTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

        self.data_dir = self.root / "data"
        self.db_path = self.data_dir / "agroscan.db"
        self.images_dir = self.data_dir / "images"
        self.backup_dir = self.data_dir / "backups"

        self.images_dir.mkdir(parents=True)
        self.backup_dir.mkdir(parents=True)

        # Base de datos SQLite aislada para las pruebas.
        self.create_database(
            [(1, "images/evidencia-01.png")]
        )

        # Imagen de prueba.
        self.image_path = self.images_dir / "evidencia-01.png"
        self.image_path.write_bytes(b"IMAGEN-DE-PRUEBA-AGROP53")

        # Sustituir rutas reales por directorios temporales.
        self.patches = [
            patch.object(backup_service, "DATA_DIR", self.data_dir),
            patch.object(backup_service, "DB_PATH", self.db_path),
            patch.object(backup_service, "IMAGES_DIR", self.images_dir),
            patch.object(backup_service, "BACKUP_DIR", self.backup_dir),
            patch.object(backup_service, "engine", Mock()),
        ]

        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def tearDown(self):
        self.tmp.cleanup()


    def create_database(self, rows):
        self.data_dir.mkdir(parents=True, exist_ok=True)

        connection = sqlite3.connect(str(self.db_path))

        try:
            connection.execute("""
                CREATE TABLE images (
                    id INTEGER PRIMARY KEY,
                    relative_path TEXT NOT NULL
                )
            """)

            connection.executemany(
                """
                INSERT INTO images (id, relative_path)
                VALUES (?, ?)
                """,
                rows,
            )

            connection.commit()

        finally:
            connection.close()


    def create_test_backup(self):
        result = backup_service.create_backup()
        return Path(result["path"])

    def test_crea_respaldo_completo(self):
        result = backup_service.create_backup()

        backup_path = Path(result["path"])

        self.assertTrue(backup_path.is_file())
        self.assertGreater(backup_path.stat().st_size, 0)

        self.assertEqual(result["imageFiles"], 1)
        self.assertEqual(result["evaluationImages"], 1)

        with zipfile.ZipFile(backup_path, "r") as archive:
            names = archive.namelist()

            self.assertIn("manifest.json", names)
            self.assertIn("database/agroscan.db", names)
            self.assertIn(
                "payload/images/evidencia-01.png",
                names,
            )

            manifest = json.loads(
                archive.read("manifest.json")
            )

            self.assertEqual(manifest["version"], 1)
            self.assertEqual(
                manifest["evaluationImageCount"],
                1,
            )

    def test_verifica_integridad_del_respaldo(self):
        backup_path = self.create_test_backup()

        staging = self.root / "staging"

        result = backup_service.prepare_restore(
            backup_path,
            staging,
        )

        self.assertTrue(result["verified"])
        self.assertEqual(
            result["evaluationImageCount"],
            1,
        )

        restored_image = (
            staging / "images" / "evidencia-01.png"
        )

        self.assertTrue(restored_image.is_file())

        self.assertEqual(
            restored_image.read_bytes(),
            b"IMAGEN-DE-PRUEBA-AGROP53",
        )


    def test_restaura_base_de_datos_e_imagenes(self):
        backup_path = self.create_test_backup()

        # Simular información modificada después del respaldo.
        with closing(sqlite3.connect(str(self.db_path))) as connection:
            connection.execute("DELETE FROM images")
            connection.execute(
                """
                INSERT INTO images (id, relative_path)
                VALUES (?, ?)
                """,
                (2, "images/actual.png"),
            )
            connection.commit()

        # Sustituir también la imagen original.
        self.image_path.unlink()

        current_image = self.images_dir / "actual.png"
        current_image.write_bytes(b"IMAGEN-ACTUAL")

        # Ejecutar restauración.
        result = backup_service.restore_backup(backup_path)

        self.assertTrue(result["restored"])
        self.assertTrue(result["verified"])
        self.assertEqual(result["evaluationImages"], 1)

        # Verificar que volvió la información original.
        with closing(sqlite3.connect(str(self.db_path))) as connection:
            rows = connection.execute(
                "SELECT id, relative_path FROM images"
            ).fetchall()

        self.assertEqual(
            rows,
            [(1, "images/evidencia-01.png")],
        )

        restored_image = (
            self.images_dir / "evidencia-01.png"
        )

        self.assertTrue(restored_image.is_file())

        self.assertEqual(
            restored_image.read_bytes(),
            b"IMAGEN-DE-PRUEBA-AGROP53",
        )

        self.assertFalse(current_image.exists())


    def test_respaldo_incluye_transacciones_confirmadas_en_wal(self):
        with closing(sqlite3.connect(str(self.db_path))) as connection:
            self.assertEqual(connection.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
            connection.execute("PRAGMA wal_autocheckpoint=0")
            connection.execute(
                "INSERT INTO images VALUES (?, ?)",
                (2, "images/wal.png"),
            )
            connection.commit()
            (self.images_dir / "wal.png").write_bytes(b"WAL-SINTETICO")
            self.assertTrue(Path(str(self.db_path) + "-wal").is_file())
            backup_path = self.create_test_backup()
            prepared = backup_service.prepare_restore(backup_path, self.root / "wal-staging")
            with closing(sqlite3.connect(prepared["database"])) as restored:
                self.assertEqual(restored.execute("SELECT COUNT(*) FROM images").fetchone()[0], 2)
            self.assertEqual((self.root / "wal-staging/images/wal.png").read_bytes(), b"WAL-SINTETICO")

    def test_rollback_recupera_estado_previo_si_falla_validacion_final(self):
        backup_path = self.create_test_backup()
        # Estado posterior al respaldo, siempre dentro del directorio temporal.
        with closing(sqlite3.connect(str(self.db_path))) as connection:
            connection.execute("UPDATE images SET relative_path = 'images/actual.png'")
            connection.commit()
        self.image_path.unlink()
        current = self.images_dir / "actual.png"
        current.write_bytes(b"ESTADO-ACTUAL-SINTETICO")
        original_database = self.db_path.read_bytes()
        validate = backup_service.validate_database
        calls = 0

        def fail_final_validation(path):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise backup_service.BackupError("Fallo final simulado")
            return validate(path)

        with patch.object(backup_service, "validate_database", side_effect=fail_final_validation):
            with self.assertRaisesRegex(backup_service.BackupError, "Fallo final simulado"):
                backup_service.restore_backup(backup_path)

        self.assertEqual(calls, 2)
        self.assertEqual(self.db_path.read_bytes(), original_database)
        self.assertEqual(current.read_bytes(), b"ESTADO-ACTUAL-SINTETICO")
        self.assertFalse(self.image_path.exists())
        self.assertEqual(validate(self.db_path)["imagePaths"], ["images/actual.png"])

    def leave_residual_wal(self):
        # Una conexión terminada abruptamente deja commits en WAL, sin handles abiertos.
        subprocess.run([
            sys.executable, "-c",
            "import os, sqlite3, sys; "
            "db=sqlite3.connect(sys.argv[1]); "
            "db.execute('PRAGMA journal_mode=WAL'); "
            "db.execute('PRAGMA wal_autocheckpoint=0'); "
            "db.execute(\"UPDATE images SET relative_path='images/actual.png'\"); "
            "db.commit(); os._exit(0)",
            str(self.db_path),
        ], check=True, timeout=15)
        self.assertTrue(Path(str(self.db_path) + "-wal").is_file())
        self.image_path.unlink()
        (self.images_dir / "actual.png").write_bytes(b"POST-BACKUP")

    def test_restaura_sin_reaplicar_wal_residual_tras_cierre_abrupto(self):
        backup_path = self.create_test_backup()
        self.leave_residual_wal()
        result = backup_service.restore_backup(backup_path)

        self.assertTrue(result["verified"])
        self.assertEqual(backup_service.validate_database(self.db_path)["imagePaths"],
                         ["images/evidencia-01.png"])
        self.assertEqual(self.image_path.read_bytes(), b"IMAGEN-DE-PRUEBA-AGROP53")
        with closing(sqlite3.connect(str(self.db_path))) as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")

    def test_rollback_conserva_commits_wal_y_fotos_ante_fallo_de_instalacion(self):
        backup_path = self.create_test_backup()
        self.leave_residual_wal()
        real_replace = backup_service.os.replace

        def fail_install(source, destination):
            if Path(source).name == 'images' and Path(destination) == self.images_dir:
                # La devolución desde rollback sí debe poder completarse.
                if Path(source).parent.name != 'rollback':
                    raise OSError('FALLO-INSTALACION-SINTETICO')
            return real_replace(source, destination)

        with patch.object(backup_service.os, 'replace', side_effect=fail_install):
            with self.assertRaisesRegex(OSError, 'FALLO-INSTALACION-SINTETICO'):
                backup_service.restore_backup(backup_path)
        self.assertEqual(backup_service.validate_database(self.db_path)['imagePaths'],
                         ['images/actual.png'])
        self.assertEqual((self.images_dir / 'actual.png').read_bytes(), b'POST-BACKUP')
        self.assertFalse(self.image_path.exists())
        with closing(sqlite3.connect(str(self.db_path))) as db:
            self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0], 'wal')

    def test_restore_rechaza_lector_wal_activo_sin_sustituir_archivos(self):
        backup_path = self.create_test_backup()
        real_connect = sqlite3.connect
        with closing(real_connect(str(self.db_path))) as writer, \
                closing(real_connect(str(self.db_path))) as reader:
            writer.execute('PRAGMA journal_mode=WAL')
            reader.execute('BEGIN')
            reader.execute('SELECT * FROM images').fetchall()
            writer.execute("UPDATE images SET relative_path='images/actual.png'")
            writer.commit()
            self.image_path.unlink()
            current = self.images_dir / 'actual.png'
            current.write_bytes(b'ACTUAL-CON-LECTOR')

            def short_timeout(*args, **kwargs):
                kwargs['timeout'] = 0.02
                return real_connect(*args, **kwargs)

            with patch.object(backup_service.sqlite3, 'connect', side_effect=short_timeout), \
                    patch.object(backup_service.os, 'replace') as replace:
                with self.assertRaisesRegex(backup_service.BackupError, 'ocupado'):
                    backup_service.restore_backup(backup_path)
                replace.assert_not_called()
            self.assertEqual(current.read_bytes(), b'ACTUAL-CON-LECTOR')
            self.assertEqual(writer.execute('SELECT relative_path FROM images').fetchone()[0],
                             'images/actual.png')
            reader.rollback()

    def test_rechaza_respaldo_inexistente(self):
        with self.assertRaises(backup_service.BackupError):
            backup_service.prepare_restore(
                self.root / "inexistente.zip",
                self.root / "staging",
            )

    def test_rechaza_archivo_que_no_es_zip(self):
        invalid_file = self.root / "invalido.zip"
        invalid_file.write_bytes(b"ARCHIVO INVALIDO")

        with self.assertRaises(backup_service.BackupError):
            backup_service.prepare_restore(
                invalid_file,
                self.root / "staging",
            )

    def test_rechaza_respaldo_con_imagen_alterada(self):
        backup_path = self.create_test_backup()

        tampered_backup = self.root / "alterado.zip"

        # Alterar el contenido sin modificar el SHA-256
        # declarado en el manifiesto.
        with zipfile.ZipFile(backup_path, "r") as source:
            with zipfile.ZipFile(
                tampered_backup,
                "w",
                compression=zipfile.ZIP_DEFLATED,
            ) as destination:

                for name in source.namelist():
                    content = source.read(name)

                    if name == "payload/images/evidencia-01.png":
                        content = b"IMAGEN-ALTERADA"

                    destination.writestr(name, content)

        original_database = self.db_path.read_bytes()
        original_image = self.image_path.read_bytes()

        with self.assertRaises(backup_service.BackupError):
            backup_service.restore_backup(tampered_backup)

        # El sistema original debe permanecer intacto.
        self.assertEqual(
            self.db_path.read_bytes(),
            original_database,
        )

        self.assertEqual(
            self.image_path.read_bytes(),
            original_image,
        )

    def test_rechaza_rutas_inseguras_en_el_zip(self):
        backup_path = self.create_test_backup()

        malicious_backup = self.root / "malicioso.zip"

        with zipfile.ZipFile(backup_path, "r") as source:
            with zipfile.ZipFile(
                malicious_backup,
                "w",
                compression=zipfile.ZIP_DEFLATED,
            ) as destination:

                for name in source.namelist():
                    destination.writestr(
                        name,
                        source.read(name),
                    )

                destination.writestr(
                    "../archivo_malicioso.txt",
                    b"CONTENIDO NO PERMITIDO",
                )

        with self.assertRaises(backup_service.BackupError):
            backup_service.prepare_restore(
                malicious_backup,
                self.root / "staging",
            )


    def test_rechaza_imagen_asociada_que_no_existe(self):
        with closing(sqlite3.connect(str(self.db_path))) as connection:
            connection.execute("DELETE FROM images")
            connection.execute(
                """
                INSERT INTO images (id, relative_path)
                VALUES (?, ?)
                """,
                (3, "images/no-existe.png"),
            )
            connection.commit()

        with self.assertRaises(backup_service.BackupError):
            backup_service.create_backup()

        # No debe publicarse un respaldo incompleto.
        self.assertEqual(
            list(self.backup_dir.glob("*.zip")),
            [],
        )


if __name__ == "__main__":
    unittest.main()
