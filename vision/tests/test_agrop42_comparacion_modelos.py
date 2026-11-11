"""Pruebas AGROP-42 con fixtures sintéticos; no acreditan precisión agronómica."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from vision.evaluation.agrop42.auditar_revisiones import COLUMNAS
from vision.evaluation.agrop42.comparar_modelos import comparar, predecir_reglas


class TestComparadorAGROP42(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ann = self.root / "anotaciones.csv"
        self.attrs = self.root / "atributos.csv"
        self.rules = self.root / "reglas.json"

    def write_csv(self, path, rows, fields):
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def make_rows(self, count=12, labels=True, views=1):
        annotations, attributes = [], []

        for i in range(count):
            label = ("E0" if i % 2 == 0 else "E1") if labels else ""

            for view in range(views):
                rid = f"REG-{i+1:03d}-V{view+1}"
                row = {key: "" for key in COLUMNAS}

                row.update({
                    "registro_id": rid,
                    "producto": "mango",
                    "sha256": f"{i*views+view+1:064x}",
                    "archivo": f"images/{rid}.jpg",
                    "estado_revision": "revisada",
                    "etiqueta_visual": label,
                    "revisor_id": "revisor-prueba" if labels else "",
                    "revisado_en": "2026-11-07T10:00:00-05:00" if labels else "",
                    "rubrica_version": "kent-ext-v0.5" if labels else "",
                    "calidad_confirmada": "true" if labels else "",
                    "cobertura_confirmada": "true" if labels else "",
                    "pieza_confirmada": "true" if labels else "",
                    "sesion_confirmada": "true" if labels else "",
                    "lote_id": "LOTE-01" if labels else "",
                    "pieza_id": f"PIEZA-{i+1:03d}" if labels else "",
                    "sesion_id": f"SESION-{i+1:03d}-V{view+1}" if labels else "",
                    "dispositivo_id": "CAM-01" if labels else "",
                    "evidencia_pieza": "evidencia/pieza" if labels else "",
                    "evidencia_sesion": "evidencia/sesion" if labels else "",
                    "justificacion_etiqueta": "Revisión humana de prueba" if labels else "",
                })

                annotations.append(row)

                red = 55 if label == "E0" else 205

                attributes.append({
                    "registro_id": rid,
                    "r_mediana": red + view,
                    "g_mediana": 100,
                    "b_mediana": 80,
                    "area_relativa": 0.55,
                    "mascara_confirmada": "true",
                    "evidencia_mascara": f"evidencias/{rid}.png",
                })

        self.write_csv(self.ann, annotations, sorted(COLUMNAS))
        self.write_csv(self.attrs, attributes, list(attributes[0]))

        config = {
            "version": "agrop42-reglas-clasicas-v1",
            "productos": {
                "mango": {
                    "rubrica_version": "kent-ext-v0.5",
                    "clase_por_defecto": "E0",
                    "reglas": [{
                        "id": "R-MANGO-01",
                        "etiqueta": "E1",
                        "condiciones": [{
                            "atributo": "r_mediana",
                            "operador": "gte",
                            "valor": 128
                        }]
                    }]
                }
            }
        }

        self.rules.write_text(json.dumps(config), encoding="utf-8")

    def test_bloquea_sin_etiquetas_verificadas(self):
        self.make_rows(labels=False)
        result = comparar(self.ann, self.attrs, self.rules)

        self.assertEqual(
            result["estado"],
            "bloqueado_por_datos_insuficientes"
        )
        self.assertFalse(result["comparacion_mismo_conjunto_prueba"])

    def test_compara_ambos_metodos_en_mismos_splits(self):
        self.make_rows()

        result = comparar(
            self.ann, self.attrs, self.rules,
            splits=25, repeticiones=3
        )

        self.assertEqual(result["estado"], "comparacion_parcial")
        self.assertEqual(result["productos_evaluados"], ["mango"])

        mango = result["productos"]["mango"]

        self.assertGreater(len(mango["resultados"]), 0)

        for fold in mango["resultados"]:
            self.assertTrue(
                set(fold["train_grupos"]).isdisjoint(fold["test_grupos"])
            )

            self.assertEqual(
                len(fold["reglas_clasicas"]["predicciones"]),
                len(fold["modelo_ligero"]["predicciones"])
            )

            self.assertEqual(
                len(fold["modelo_ligero"]["predicciones"]),
                len(fold["test_registros"])
            )

    def test_varias_vistas_de_una_pieza_se_agregan(self):
        self.make_rows(views=2)

        result = comparar(
            self.ann, self.attrs, self.rules,
            splits=25, repeticiones=2
        )

        mango = result["productos"]["mango"]

        self.assertEqual(mango["fotografias_utilizadas"], 24)
        self.assertEqual(mango["piezas_utilizadas"], 12)

    def test_mascara_no_confirmada_bloquea(self):
        self.make_rows()

        with self.attrs.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))

        rows[0]["mascara_confirmada"] = "false"
        self.write_csv(self.attrs, rows, list(rows[0]))

        result = comparar(self.ann, self.attrs, self.rules)

        self.assertEqual(
            result["estado"],
            "bloqueado_por_insumos_invalidos"
        )

    def test_rubrica_distinta_bloquea(self):
        self.make_rows()

        config = json.loads(self.rules.read_text(encoding="utf-8"))
        config["productos"]["mango"]["rubrica_version"] = "otra-rubrica"
        self.rules.write_text(json.dumps(config), encoding="utf-8")

        result = comparar(self.ann, self.attrs, self.rules)

        self.assertEqual(
            result["estado"],
            "bloqueado_por_insumos_invalidos"
        )

    def test_reglas_respetan_primera_coincidencia(self):
        config = {
            "clase_por_defecto": "E0",
            "reglas": [
                {
                    "id": "R1",
                    "etiqueta": "E1",
                    "condiciones": [{
                        "atributo": "r_mediana",
                        "operador": "gte",
                        "valor": 100
                    }]
                },
                {
                    "id": "R2",
                    "etiqueta": "E2",
                    "condiciones": [{
                        "atributo": "r_mediana",
                        "operador": "gte",
                        "valor": 150
                    }]
                }
            ]
        }

        self.assertEqual(
            predecir_reglas([[180, 10, 10, .5]], config),
            ["E1"]
        )

        self.assertEqual(
            predecir_reglas([[50, 10, 10, .5]], config),
            ["E0"]
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)