"""AG-046 BKP-05: prueba ESTRICTA de bloqueo durante restauracion.

NO se convierte una escritura concurrente en 'aprobada'. Si el backend
acepta un alta de lote durante suspend_capture(), debe FALLAR esta prueba:
el ejecutor reporta el hallazgo como BRECHA_BKP05_CONFIRMADA. La prueba
usa exclusivamente SQLite temporal y no inicia restauracion destructiva.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import Base, enable_sqlite_foreign_keys, get_db
from app.main import app
from app.models import Role, User
from app.security import create_access_token
from app.services.capture_control import suspend_capture


class AG046I03BKP05Tests(unittest.TestCase):
    def test_bkp05_alta_lote_debe_bloquearse_durante_restauracion(self):
        with tempfile.TemporaryDirectory(prefix='ag046-bkp05-') as folder:
            db_file = Path(folder) / 'instance.sqlite'
            engine = create_engine(
                f'sqlite:///{db_file.as_posix()}',
                connect_args={'check_same_thread': False, 'timeout': 5},
            )
            event.listen(engine, 'connect', enable_sqlite_foreign_keys)
            Base.metadata.create_all(engine)
            Session = sessionmaker(engine, expire_on_commit=False)
            with Session() as db:
                user = User(username='ag046_operator', full_name='Test operador',
                            password_hash='TEST_NO_LOGIN', roles=[Role(name='operador')],
                            is_active=True)
                db.add(user)
                db.commit()
                operator_id = user.id

            def isolated_db():
                with Session() as db:
                    yield db

            app.dependency_overrides[get_db] = isolated_db
            try:
                with TestClient(app) as client:
                    with suspend_capture():
                        # Verificar distintas operaciones persistentes. El
                        # middleware debe rechazar antes de ejecutar las rutas.
                        cases = (
                            ('POST', '/api/lots', {'code': 'AG046-BKP05', 'product': 'mango', 'responsible': 'test'}),
                            ('POST', '/api/evaluations', {}),
                            ('POST', '/api/iot/measurements', {}),
                            ('PATCH', '/api/users/1/status', {'isActive': False}),
                            ('POST', '/api/evaluations/E-000001/review-decisions', {}),
                        )
                        for method, endpoint, payload in cases:
                            with self.subTest(method=method, endpoint=endpoint):
                                response = client.request(
                                    method, endpoint,
                                    headers={'Authorization': 'Bearer ' + create_access_token(operator_id)},
                                    json=payload,
                                )
                                # HTTP 201/200/422/401/403 antes del guard
                                # invalida la garantía durante suspensión.
                                self.assertEqual(response.status_code, 503,
                                    f'Escritura no bloqueada: {method} {endpoint} devolvió HTTP {response.status_code}')
                    with Session() as db:
                        from sqlalchemy import select
                        from app.models import Lot
                        self.assertIsNone(db.scalar(select(Lot).where(Lot.code == 'AG046-BKP05')))
            finally:
                app.dependency_overrides.pop(get_db, None)
                engine.dispose()


if __name__ == '__main__':
    unittest.main()
