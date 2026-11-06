"""Pruebas del AUDITOR, no prueba de exactitud visual ni dataset agronómico."""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from contextlib import closing
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from vision.evaluation.agrop42.auditar import (
    AuditInputError, _read_annotations, audit, main, run,
)


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "backend/data"
        self.data.mkdir(parents=True)
        self.db = self.data / "agroscan.db"
        self.manifests = self.root / "vision/experiments"
        self.manifests.mkdir(parents=True)

    def picture(self, name: str, color=(120, 130, 40)) -> tuple[str, str]:
        import hashlib
        path = self.data / "images" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (144, 144), color).save(path)
        return "images/" + name, hashlib.sha256(path.read_bytes()).hexdigest()

    def db_fixture(self, entries):
        with closing(sqlite3.connect(self.db)) as con:
            con.executescript("""
            CREATE TABLE lots (id INTEGER PRIMARY KEY, code TEXT, product TEXT);
            CREATE TABLE evaluations (id INTEGER PRIMARY KEY, lot_id INTEGER,
                piece_ref_id INTEGER, piece_id TEXT, device_id TEXT, boot_id TEXT,
                visual_category TEXT, product TEXT);
            CREATE TABLE images (id INTEGER PRIMARY KEY, evaluation_id INTEGER, relative_path TEXT);
            INSERT INTO lots VALUES (1, 'M1', 'mango'), (2, 'T1', 'tomate');
            """)
            for n, (product, piece, dev, boot, path, visual_label) in enumerate(entries, 1):
                lot_id = 1 if product == "mango" else 2
                con.execute("INSERT INTO evaluations VALUES (?,?,?,?,?,?,?,?)",
                            (n, lot_id, piece, f"P-{piece}", dev, boot, visual_label, product))
                con.execute("INSERT INTO images VALUES (?,?,?)", (n, n, path))
            con.commit()

    @staticmethod
    def record(n, product="mango", sha=None, piece=None, session=None, unverified=None):
        return {
            "source_id": f"test:{n}", "source": "test", "product": product,
            "piece_key": f"piece:{piece}" if piece is not None else None,
            "session_key": f"session:{session}" if session is not None else None,
            "file_status": "valida" if sha else "archivo_ausente",
            "sha256": sha, "unverified_label": unverified,
        }

    @staticmethod
    def annotation(sha, label="E0", product="mango", reviewed=True):
        return {"sha256": sha, "label": label, "product": product,
                "review_documented": reviewed}

    def audit_rows(self, rows, annotations=()):
        return audit(rows, list(annotations), {})

    def test_sin_db_no_inventa_cero_fotografias_disponibles(self):
        report = run(self.db, self.data, self.root)
        self.assertEqual(report["status"], "insumos_no_disponibles")
        self.assertEqual(report["fuentes"]["sqlite"]["status"], "no_disponible")
        self.assertFalse(report["decision"]["entrenamiento_ejecutado"])

    def test_base_sqlite_solo_lectura_evidencia_real_del_archivo(self):
        path, sha = self.picture("fruto.png")
        self.db_fixture([("mango", 1, "D1", "S1", path, "E0")])
        before = self.db.read_bytes()
        report = run(self.db, self.data, self.root)
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(report["totales"]["archivos_unicos_sha256"], 1)
        self.assertEqual(report["por_producto"]["mango"]["grupos_independientes_verificables"], 1)
        self.assertEqual(report["por_producto"]["mango"]["etiquetas_no_verificadas_en_origen"], 1)
        self.assertEqual(report["por_producto"]["mango"]["imagenes_con_revision_documentada"], 0)
        self.assertEqual(len(sha), 64)

    def test_base_con_esquema_incorrecto_da_error(self):
        sqlite3.connect(self.db).close()
        with self.assertRaises(AuditInputError):
            run(self.db, self.data, self.root)

    def test_imagenes_duplicadas_por_sha_no_suman_grupos(self):
        path, sha = self.picture("a.png")
        self.db_fixture([("mango", 1, "D1", "S1", path, None),
                         ("mango", 2, "D2", "S2", path, None)])
        report = run(self.db, self.data, self.root)
        self.assertEqual(report["totales"]["sha256_repetidos"], 1)
        self.assertEqual(report["por_producto"]["mango"]["grupos_independientes_verificables"], 1)
        self.assertEqual(len(report["evidencia_de_duplicados"][0]["registros"]), 2)
        self.assertEqual(report["evidencia_de_duplicados"][0]["sha256"], sha)

    def test_sesion_compartida_une_piezas_distintas(self):
        a, _ = self.picture("a.png", (10, 170, 40))
        b, _ = self.picture("b.png", (20, 150, 40))
        self.db_fixture([("mango", 1, "D1", "S1", a, None),
                         ("mango", 2, "D1", "S1", b, None)])
        report = run(self.db, self.data, self.root)
        self.assertEqual(report["por_producto"]["mango"]["imagenes_unicas_sha256"], 2)
        self.assertEqual(report["por_producto"]["mango"]["grupos_independientes_verificables"], 1)

    def test_sin_sesion_no_afirma_independencia(self):
        path, _ = self.picture("a.png")
        self.db_fixture([("mango", 1, "D1", None, path, None)])
        report = run(self.db, self.data, self.root)
        self.assertEqual(report["por_producto"]["mango"]["registros_con_pieza_y_sesion"], 0)
        self.assertEqual(report["por_producto"]["mango"]["grupos_independientes_verificables"], 0)

    def test_ruta_escapada_se_rechaza(self):
        self.db_fixture([("mango", 1, "D1", "S1", "../../../etc/passwd", None)])
        report = run(self.db, self.data, self.root)
        self.assertEqual(report["totales"]["registros_con_archivos_ausentes_o_invalidos"], 1)
        self.assertEqual(report["totales"]["archivos_unicos_sha256"], 0)

    def test_archivo_corrupto_se_rechaza(self):
        (self.data / "x.png").write_text("esto no es PNG", encoding="utf-8")
        self.db_fixture([("mango", 1, "D1", "S1", "x.png", None)])
        report = run(self.db, self.data, self.root)
        self.assertEqual(report["totales"]["registros_de_archivos_validos"], 0)

    def test_duplicado_de_imagen_entre_productos_bloquea(self):
        sha = "a" * 64
        rows = [self.record("1", "mango", sha, 1, 1),
                self.record("2", "tomate", sha, 2, 2)]
        report = self.audit_rows(rows)
        self.assertEqual(report["totales"]["hashes_reutilizados_entre_productos"], 1)
        self.assertIn("mismo_archivo_asignado_a_productos_distintos",
                      report["por_producto"]["mango"]["motivos"])

    def test_falta_de_etiquetas_revisadas_bloquea(self):
        rows = [self.record(str(n), sha=f"{n:064x}", piece=n, session=n, unverified="E0")
                for n in range(1, 9)]
        report = self.audit_rows(rows)
        self.assertEqual(report["por_producto"]["mango"]["grupos_independientes_verificables"], 8)
        self.assertIn("menos_de_dos_clases_con_etiquetas_revisadas_y_sesion",
                      report["por_producto"]["mango"]["motivos"])
        self.assertFalse(report["decision"]["metricas_predictivas_calculadas"])

    def test_solo_anotaciones_revisadas_cuentan(self):
        rows = [self.record(str(n), sha=f"{n:064x}", piece=n, session=n) for n in range(1, 7)]
        ann = [self.annotation(f"{n:064x}", "E0" if n <= 3 else "E1", reviewed=n != 6)
               for n in range(1, 7)]
        report = self.audit_rows(rows, ann)
        self.assertEqual(report["por_producto"]["mango"]["status"], "bloqueado")
        self.assertIn("alguna_clase_tiene_menos_de_tres_grupos_independientes",
                      report["por_producto"]["mango"]["motivos"])

    def test_dos_clases_tres_grupos_cada_una_solo_autorizan_intentar_particion(self):
        rows = [self.record(str(n), sha=f"{n:064x}", piece=n, session=n) for n in range(1, 7)]
        ann = [self.annotation(f"{n:064x}", "E0" if n <= 3 else "E1")
               for n in range(1, 7)]
        report = self.audit_rows(rows, ann)
        self.assertEqual(report["status"], "potencial_para_particion_por_producto")
        self.assertEqual(report["por_producto"]["mango"]["status"], "preparado_para_intentar_particion")
        self.assertFalse(report["decision"]["entrenamiento_ejecutado"])

    def test_etiquetas_contradictorias_bloquean(self):
        rows = [self.record(str(n), sha=f"{n:064x}", piece=n, session=n) for n in range(1, 7)]
        ann = [self.annotation(f"{n:064x}", "E0" if n <= 3 else "E1") for n in range(1, 7)]
        ann.append(self.annotation(f"{1:064x}", "E1"))
        report = self.audit_rows(rows, ann)
        self.assertIn("anotaciones_contradicen_la_misma_imagen_o_grupo",
                      report["por_producto"]["mango"]["motivos"])

    def test_etiquetas_de_dos_productos_no_se_mezclan(self):
        rows, ann = [], []
        for n in range(1, 7):
            product = "mango" if n <= 3 else "tomate"
            rows.append(self.record(str(n), product, f"{n:064x}", n, n))
            ann.append(self.annotation(f"{n:064x}", "E0" if n % 2 else "E1", product))
        report = self.audit_rows(rows, ann)
        self.assertEqual(report["status"], "bloqueado_por_datos_insuficientes")
        self.assertEqual(report["por_producto"]["mango"]["status"], "bloqueado")
        self.assertEqual(report["por_producto"]["tomate"]["status"], "bloqueado")

    def test_manifest_no_confiere_sesion_automaticamente(self):
        path, sha = self.picture("fruit.png")
        manifest = {
            "piece": {"product": "mango", "lot_id": "L1", "piece_id": "P1"},
            "images": [{"image_id": "I1", "path": "../../backend/data/" + path}],
        }
        (self.manifests / "mi_mango.json").write_text(json.dumps(manifest), encoding="utf-8")
        (self.manifests / "resultado_mango.json").write_text(json.dumps({
            "task": "AGROP-40", "piece": manifest["piece"],
            "images": [{"image_id": "I1", "status": "valida"}],
            "criteria": {"R01": {}}, "visual_status": "pendiente_revision"
        }), encoding="utf-8")
        report = run(self.db, self.data, self.root, self.manifests)
        self.assertEqual(report["fuentes"]["manifiestos"]["manifests"], 1)
        self.assertEqual(report["por_producto"]["mango"]["imagenes_unicas_sha256"], 1)
        self.assertEqual(report["por_producto"]["mango"]["grupos_independientes_verificables"], 0)
        self.assertEqual(report["evidencia_de_duplicados"], [])
        self.assertEqual(len(sha), 64)

    def test_anotacion_sin_credenciales_no_cuenta(self):
        data = {"annotations": [{"sha256": "a" * 64, "product": "mango", "label": "E0",
                                 "review_verified": True, "reviewer_id": "", "reviewed_at": "2026-11-05",
                                 "rubric_version": "kent-ext-v0.5"}]}
        path = self.root / "labels.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        rows, info = _read_annotations(path)
        self.assertEqual(info["con_revision_documentada"], 0)
        self.assertFalse(rows[0]["review_documented"])

    def test_anotacion_invalida_falla_explicitamente(self):
        path = self.root / "labels.json"
        path.write_text(json.dumps({"annotations": [{"sha256": "BAD", "product": "mango",
                                                    "label": "E0"}]}), encoding="utf-8")
        with self.assertRaises(AuditInputError):
            _read_annotations(path)

    def test_cli_informe_reproducible_sin_timestamp_volatil(self):
        path, _ = self.picture("a.png")
        self.db_fixture([("mango", 1, "D1", "S1", path, None)])
        output = self.root / "auditoria.json"
        args = ["--db", str(self.db), "--data-root", str(self.data),
                "--allowed-root", str(self.root), "--output", str(output)]
        self.assertEqual(main(args), 0)
        before = output.read_bytes()
        self.assertEqual(main(args), 0)
        self.assertEqual(output.read_bytes(), before)

    def test_seis_registros_de_tomate_pueden_ser_tres_archivos_unicos(self):
        paths = [self.picture(f"tomate_{i}.png", (170 + i, 40, 20))[0] for i in range(3)]
        for piece in range(3):
            manifest = {
                "piece": {"product": "tomate", "lot_id": "L", "piece_id": f"T{piece}"},
                "images": [
                    {"image_id": f"A{piece}", "path": "../../backend/data/" + paths[(piece * 2) % 3]},
                    {"image_id": f"B{piece}", "path": "../../backend/data/" + paths[(piece * 2 + 1) % 3]},
                ],
            }
            (self.manifests / f"manifest_{piece}.json").write_text(json.dumps(manifest), encoding="utf-8")
        report = run(self.db, self.data, self.root, self.manifests)
        self.assertEqual(report["por_producto"]["tomate"]["registros"], 6)
        self.assertEqual(report["por_producto"]["tomate"]["imagenes_unicas_sha256"], 3)
        self.assertEqual(report["por_producto"]["tomate"]["grupos_independientes_verificables"], 0)
        self.assertEqual(report["totales"]["sha256_repetidos"], 3)

    def test_manifest_sesion_explicita_permite_formar_grupo(self):
        path, sha = self.picture("fruit.png")
        manifest = {
            "piece": {"product": "mango", "lot_id": "L1", "piece_id": "P1"},
            "images": [{"path": "../../backend/data/" + path,
                        "capture": {"device_id": "ESP32-A", "boot_id": "BOOT-123"}}],
        }
        (self.manifests / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        report = run(self.db, self.data, self.root, self.manifests)
        self.assertEqual(report["por_producto"]["mango"]["grupos_independientes_verificables"], 1)
        self.assertEqual(report["por_producto"]["mango"]["imagenes_unicas_sha256"], 1)
        self.assertEqual(len(sha), 64)

    def test_etiquetas_contradictorias_en_una_sesion_bloquean(self):
        rows = [self.record(str(n), sha=f"{n:064x}", piece=n, session=1 if n in (1, 2) else n)
                for n in range(1, 7)]
        ann = [self.annotation(f"{n:064x}", "E0" if n <= 1 or n == 3 else "E1")
               for n in range(1, 7)]
        report = self.audit_rows(rows, ann)
        self.assertEqual(report["por_producto"]["mango"]["grupos_con_etiquetas_contradictorias"], 1)
        self.assertIn("anotaciones_contradicen_la_misma_imagen_o_grupo",
                      report["por_producto"]["mango"]["motivos"])


if __name__ == "__main__":
    unittest.main()
