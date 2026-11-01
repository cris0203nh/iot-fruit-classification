"""AGROP-30 / AG-022: lotes, identidad de pieza y CRUD de datos demo.

Todas las operaciones se realizan sobre SQLite en memoria, nunca sobre
backend/data/agroscan.db. U/D se prueban en ORM: no existen rutas HTTP
PATCH/DELETE para lotes o piezas en el contrato actual.
"""

import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Evaluation, Lot, Piece


class AGROP30LotsPiecesTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)

        def isolated_db():
            with Session(self.engine) as session:
                yield session

        app.dependency_overrides[get_db] = isolated_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.pop(get_db, None)
        self.engine.dispose()

    def create_lot(self, code="DEMO-MANGO-01", product="mango"):
        return self.client.post(
            "/api/lots",
            json={"code": code, "product": product, "responsible": "DEMO"},
        )

    def register(self, code, piece="DEMO-P001"):
        return self.client.post(
            "/api/evaluations", json={"lotId": code, "pieceId": piece}
        )

    def test_creacion_y_consulta_de_lote_abierto(self):
        created = self.create_lot()
        self.assertEqual(created.status_code, 201, created.text)
        lot = created.json()
        self.assertEqual(lot["code"], "DEMO-MANGO-01")
        self.assertEqual(lot["product"], "mango")
        self.assertEqual(lot["status"], "open")
        self.assertGreater(lot["id"], 0)
        self.assertIsNotNone(lot["created_at"])
        self.assertEqual(self.client.get(f"/api/lots/{lot['id']}").json(), lot)
        self.assertEqual(self.client.get("/api/lots").json(), [lot])

    def test_referencia_de_lote_unica_sin_distinguir_mayusculas(self):
        self.assertEqual(self.create_lot().status_code, 201)
        duplicate = self.create_lot("demo-mango-01", "tomate")
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(len(self.client.get("/api/lots").json()), 1)

    def test_producto_y_referencia_invalidos_no_crean_lotes(self):
        for code, product in [("!INVALIDO", "mango"), ("DEMO-001", "pera")]:
            with self.subTest(code=code, product=product):
                response = self.create_lot(code, product)
                self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get("/api/lots").json(), [])

    def test_registro_requiere_lote_existente(self):
        response = self.register("DEMO-NO-EXISTE")
        self.assertEqual(response.status_code, 404)
        with Session(self.engine) as db:
            self.assertEqual(len(db.scalars(select(Piece)).all()), 0)
            self.assertEqual(len(db.scalars(select(Evaluation)).all()), 0)

    def test_lote_cerrado_no_permite_registrar_piezas(self):
        lot_id = self.create_lot().json()["id"]
        # Preparación controlada: el contrato HTTP aún no expone cerrar un lote.
        with Session(self.engine) as db:
            lot = db.get(Lot, lot_id)
            lot.status = "closed"
            db.commit()
        self.assertEqual(self.register("DEMO-MANGO-01").status_code, 409)
        with Session(self.engine) as db:
            self.assertEqual(len(db.scalars(select(Piece)).all()), 0)

    def test_pieza_y_evaluacion_con_identificadores_persistidos(self):
        self.create_lot()
        response = self.register("DEMO-MANGO-01", "DEMO-P001")
        self.assertEqual(response.status_code, 201, response.text)
        saved = response.json()
        self.assertRegex(saved["id"], r"^E-\d{6}$")
        self.assertEqual(saved["pieceId"], "DEMO-P001")
        self.assertEqual(saved["lotId"], "DEMO-MANGO-01")
        self.assertEqual(saved["product"], "mango")
        self.assertEqual(saved["status"], "processing")
        self.assertIsNone(saved["weightGrams"])
        self.assertEqual(self.client.get(f"/api/evaluations/{saved['id']}").json(), saved)
        with Session(self.engine) as db:
            ev = db.scalar(select(Evaluation))
            piece = db.scalar(select(Piece))
            self.assertIsNotNone(ev.piece_ref_id)
            self.assertEqual(ev.piece_ref_id, piece.id)
            self.assertEqual(piece.lot_id, ev.lot_id)

    def test_la_misma_pieza_conserva_identidad_si_se_evalua_dos_veces(self):
        self.create_lot()
        first = self.register("DEMO-MANGO-01").json()
        second = self.register("DEMO-MANGO-01").json()
        self.assertNotEqual(first["id"], second["id"])
        with Session(self.engine) as db:
            pieces = db.scalars(select(Piece)).all()
            evaluations = db.scalars(select(Evaluation)).all()
            self.assertEqual(len(pieces), 1)
            self.assertEqual(len(evaluations), 2)
            self.assertTrue(all(ev.piece_ref_id == pieces[0].id for ev in evaluations))

    def test_no_se_mezclan_productos_entre_lotes(self):
        self.create_lot("DEMO-MANGO-01", "mango")
        self.create_lot("DEMO-TOMATE-01", "tomate")
        mango = self.register("DEMO-MANGO-01", "DEMO-P001")
        tomate = self.register("DEMO-TOMATE-01", "DEMO-P001")
        self.assertEqual(mango.status_code, 201)
        self.assertEqual(tomate.status_code, 201)
        self.assertEqual(mango.json()["product"], "mango")
        self.assertEqual(tomate.json()["product"], "tomate")
        with Session(self.engine) as db:
            pieces = db.scalars(select(Piece).order_by(Piece.id)).all()
            self.assertEqual(len(pieces), 2)
            self.assertNotEqual(pieces[0].lot_id, pieces[1].lot_id)
            self.assertNotEqual(pieces[0].id, pieces[1].id)

    def test_crud_demo_en_orm_con_actualizacion_y_eliminacion_aisladas(self):
        # La API pública cubre Create/Read; Update/Delete se prueban solo
        # sobre entidades demo sin evaluaciones, dentro de SQLite en memoria.
        with Session(self.engine) as db:
            lot = Lot(code="DEMO-CRUD-01", product="mango", responsible="DEMO")
            db.add(lot)
            db.flush()
            piece = Piece(lot_id=lot.id, code="DEMO-PIEZA-CRUD")
            db.add(piece)
            db.commit()
            lot_id, piece_id = lot.id, piece.id

        with Session(self.engine) as db:
            saved = db.get(Lot, lot_id)
            self.assertEqual(saved.code, "DEMO-CRUD-01")
            self.assertEqual(db.get(Piece, piece_id).code, "DEMO-PIEZA-CRUD")
            saved.responsible = "DEMO-EDITADO"
            db.commit()

        with Session(self.engine) as db:
            self.assertEqual(db.get(Lot, lot_id).responsible, "DEMO-EDITADO")
            db.delete(db.get(Piece, piece_id))
            db.flush()
            db.delete(db.get(Lot, lot_id))
            db.commit()
            self.assertIsNone(db.get(Piece, piece_id))
            self.assertIsNone(db.get(Lot, lot_id))

    def test_restriccion_unicidad_de_pieza_en_mismo_lote(self):
        lot_id = self.create_lot().json()["id"]
        with Session(self.engine) as db:
            db.add(Piece(lot_id=lot_id, code="DEMO-P001"))
            db.commit()
            db.add(Piece(lot_id=lot_id, code="DEMO-P001"))
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()


if __name__ == "__main__":
    unittest.main()
