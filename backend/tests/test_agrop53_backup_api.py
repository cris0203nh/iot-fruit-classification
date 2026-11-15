
import tempfile
import unittest

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Role, User
from app.security import create_access_token, hash_password
from app.routers import backup as backup_router
from app.services.backup_service import BackupError


class AGROP53BackupAPITests(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        Base.metadata.create_all(self.engine)

        self.SessionLocal = Session
        self.db = Session(self.engine)

        def override_get_db():
            yield self.db

        app.dependency_overrides[get_db] = override_get_db

        self.users = {}

        for role_name in [
            "administrador",
            "revisor",
            "operador",
        ]:
            role = Role(name=role_name)

            user = User(
                username=f"api_test_{role_name}",
                full_name=f"Usuario {role_name}",
                password_hash=hash_password("PruebaSegura123"),
                is_active=True,
            )

            user.roles.append(role)

            self.db.add(user)
            self.users[role_name] = user

        self.db.commit()

        for user in self.users.values():
            self.db.refresh(user)

        self.client = TestClient(app)

        self.tmp = tempfile.TemporaryDirectory()
        self.backup_dir = Path(self.tmp.name) / "backups"
        self.backup_dir.mkdir()

        self.backup_dir_patch = patch.object(
            backup_router,
            "BACKUP_DIR",
            self.backup_dir,
        )
        self.backup_dir_patch.start()

        self.capture_state = {"active": False}

        @contextmanager
        def fake_suspend_capture():
            self.capture_state["active"] = True
            try:
                yield
            finally:
                self.capture_state["active"] = False

        self.capture_patch = patch.object(
            backup_router,
            "suspend_capture",
            fake_suspend_capture,
        )
        self.capture_patch.start()

    def tearDown(self):
        self.client.close()

        self.capture_patch.stop()
        self.backup_dir_patch.stop()

        app.dependency_overrides.clear()

        self.db.close()
        self.engine.dispose()

        self.tmp.cleanup()

    def headers(self, role_name):
        user = self.users[role_name]
        token = create_access_token(user.id)

        return {
            "Authorization": f"Bearer {token}"
        }

    def test_administrador_puede_crear_respaldo(self):

        def fake_create_backup():
            self.assertTrue(self.capture_state["active"])

            return {
                "path": str(self.backup_dir / "respaldo.zip"),
                "filename": "respaldo.zip",
                "imageFiles": 3,
                "evaluationImages": 3,
            }

        with patch.object(
            backup_router,
            "create_backup",
            side_effect=fake_create_backup,
        ) as mocked:

            response = self.client.post(
                "/api/admin/backups",
                headers=self.headers("administrador"),
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

        self.assertNotIn(
            "path",
            response.json()["backup"],
        )

        mocked.assert_called_once()

        self.assertFalse(self.capture_state["active"])

    def test_operador_y_revisor_no_pueden_crear_respaldo(self):

        for role in ["operador", "revisor"]:
            with self.subTest(role=role):
                with patch.object(
                    backup_router,
                    "create_backup",
                ) as mocked:

                    response = self.client.post(
                        "/api/admin/backups",
                        headers=self.headers(role),
                    )

                self.assertEqual(response.status_code, 403)
                mocked.assert_not_called()

    def test_usuario_sin_token_no_puede_crear_respaldo(self):

        response = self.client.post(
            "/api/admin/backups",
        )

        self.assertEqual(response.status_code, 401)

    def test_administrador_puede_restaurar_respaldo(self):

        contenido = b"ZIP-DE-PRUEBA-AGROP53"

        def fake_restore_backup(path):

            self.assertTrue(self.capture_state["active"])
            self.assertTrue(Path(path).is_file())

            self.assertEqual(
                Path(path).read_bytes(),
                contenido,
            )

            return {
                "restored": True,
                "verified": True,
                "evaluationImages": 3,
            }

        with patch.object(
            backup_router,
            "restore_backup",
            side_effect=fake_restore_backup,
        ) as mocked:

            response = self.client.post(
                "/api/admin/backups/restore",
                headers=self.headers("administrador"),
                files={
                    "file": (
                        "respaldo.zip",
                        contenido,
                        "application/zip",
                    )
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

        self.assertTrue(
            response.json()["restoration"]["verified"]
        )

        mocked.assert_called_once()

        self.assertFalse(self.capture_state["active"])

        # El archivo temporal de carga debe eliminarse.
        self.assertEqual(
            list(self.backup_dir.iterdir()),
            [],
        )

    def test_operador_y_revisor_no_pueden_restaurar(self):

        for role in ["operador", "revisor"]:
            with self.subTest(role=role):

                with patch.object(
                    backup_router,
                    "restore_backup",
                ) as mocked:

                    response = self.client.post(
                        "/api/admin/backups/restore",
                        headers=self.headers(role),
                        files={
                            "file": (
                                "respaldo.zip",
                                b"ZIP-DE-PRUEBA",
                                "application/zip",
                            )
                        },
                    )

                self.assertEqual(response.status_code, 403)
                mocked.assert_not_called()

    def test_usuario_sin_token_no_puede_restaurar(self):

        response = self.client.post(
            "/api/admin/backups/restore",
            files={
                "file": (
                    "respaldo.zip",
                    b"ZIP-DE-PRUEBA",
                    "application/zip",
                )
            },
        )

        self.assertEqual(response.status_code, 401)

    def test_rechaza_archivo_con_extension_incorrecta(self):

        with patch.object(
            backup_router,
            "restore_backup",
        ) as mocked:

            response = self.client.post(
                "/api/admin/backups/restore",
                headers=self.headers("administrador"),
                files={
                    "file": (
                        "documento.pdf",
                        b"CONTENIDO",
                        "application/pdf",
                    )
                },
            )

        self.assertEqual(response.status_code, 422)
        mocked.assert_not_called()

    def test_rechaza_archivo_vacio(self):

        with patch.object(
            backup_router,
            "restore_backup",
        ) as mocked:

            response = self.client.post(
                "/api/admin/backups/restore",
                headers=self.headers("administrador"),
                files={
                    "file": (
                        "respaldo.zip",
                        b"",
                        "application/zip",
                    )
                },
            )

        self.assertEqual(response.status_code, 422)
        mocked.assert_not_called()

        self.assertFalse(self.capture_state["active"])

    def test_captura_se_reanuda_si_falla_restauracion(self):

        with patch.object(
            backup_router,
            "restore_backup",
            side_effect=BackupError(
                "Respaldo de prueba inválido."
            ),
        ):

            response = self.client.post(
                "/api/admin/backups/restore",
                headers=self.headers("administrador"),
                files={
                    "file": (
                        "respaldo.zip",
                        b"ZIP-INVALIDO",
                        "application/zip",
                    )
                },
            )

        self.assertEqual(response.status_code, 422)

        # El bloque finally del control debe liberar la captura.
        self.assertFalse(self.capture_state["active"])

        self.assertEqual(
            list(self.backup_dir.iterdir()),
            [],
        )


if __name__ == "__main__":
    unittest.main()
