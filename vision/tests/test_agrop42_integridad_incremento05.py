"""AGROP-42 Incremento 05: controles de integridad de la revisión documental.

Todos los registros de prueba son sintéticos y no acreditan datos agrícolas.
"""
import csv
import tempfile
import unittest
from pathlib import Path

from vision.evaluation.agrop42.auditar_revisiones import COLUMNAS, auditar_csv


class IntegridadIncremento05Tests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.csv_path = Path(tmp.name) / "revisiones.csv"

    def fila(self, indice, *, etiqueta="E0", producto="mango", pieza=None,
             sesion=None, lote="L-1", estado="revisada"):
        f = dict.fromkeys(COLUMNAS, "")
        f.update({
            "registro_id": f"REG-{indice}", "producto": producto,
            "sha256": f"{indice:064x}", "archivo": f"images/{indice}.jpg",
            "estado_revision": estado, "etiqueta_visual": etiqueta,
            "revisor_id": "revisor-prueba", "revisado_en": "2026-11-05T14:00:00-05:00",
            "rubrica_version": "version-de-prueba", "calidad_confirmada": "true",
            "cobertura_confirmada": "true", "pieza_confirmada": "true",
            "sesion_confirmada": "true", "lote_id": lote,
            "pieza_id": pieza or f"P-{indice}", "sesion_id": sesion or f"S-{indice}",
            "dispositivo_id": "D-prueba", "evidencia_pieza": "prueba-P",
            "evidencia_sesion": "prueba-S", "justificacion_etiqueta": "prueba",
        })
        return f

    def auditar(self, filas):
        with self.csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=sorted(COLUMNAS))
            writer.writeheader()
            writer.writerows(filas)
        return auditar_csv(self.csv_path)

    def test_sha_duplicado_cambiando_mayusculas_no_cuenta(self):
        a = self.fila(1)
        b = self.fila(2)
        a["sha256"] = "A" * 64
        b["sha256"] = "a" * 64
        resultado = self.auditar([a, b])
        self.assertTrue(any("SHA256 inválido o repetido" in e
                            for e in resultado["errores_integridad"]))
        self.assertEqual(resultado["productos"]["mango"]["estado"],
                         "bloqueado_por_datos_insuficientes")

    def test_ruta_windows_con_traversal_rechazada(self):
        fila = self.fila(1)
        fila["archivo"] = r"images\..\secretos.jpg"
        self.assertTrue(any("ruta relativa insegura" in x
                            for x in self.auditar([fila])["errores_integridad"]))

    def test_ruta_windows_con_unidad_rechazada(self):
        fila = self.fila(1)
        fila["archivo"] = "C:secreto.jpg"
        self.assertTrue(any("ruta relativa insegura" in x
                            for x in self.auditar([fila])["errores_integridad"]))

    def test_ruta_stream_alternativo_windows_rechazada(self):
        fila = self.fila(1)
        fila["archivo"] = "images/imagen.jpg:stream"
        self.assertTrue(any("ruta relativa insegura" in x
                            for x in self.auditar([fila])["errores_integridad"]))

    def test_fila_con_columnas_extra_rechazada(self):
        # Un DictReader con encabezado más corto agrega columnas sobrantes a None.
        self.csv_path.write_text(
            "registro_id,producto,sha256,archivo,estado_revision," +
            ",".join(sorted(COLUMNAS - {
                "registro_id", "producto", "sha256", "archivo", "estado_revision"})) +
            "\nR1,mango," + "0" * 64 + ",images/1.jpg,pendiente," +
            ",".join("" for _ in sorted(COLUMNAS - {
                "registro_id", "producto", "sha256", "archivo", "estado_revision"})) +
            ",columna_sobrante\n", encoding="utf-8")
        r = auditar_csv(self.csv_path)
        self.assertTrue(any("columnas extra" in x for x in r["errores_integridad"]))

    def test_pieza_misma_etiquetas_contradictorias_bloquean(self):
        filas = [self.fila(1, etiqueta="E0", pieza="M1", sesion="S1"),
                 self.fila(2, etiqueta="E1", pieza="M1", sesion="S2"),
                 self.fila(3, etiqueta="E0", pieza="M2", sesion="S3"),
                 self.fila(4, etiqueta="E1", pieza="M3", sesion="S4")]
        resultado = self.auditar(filas)
        self.assertTrue(any("etiquetas_contradictorias_pieza" in x
                            for x in resultado["errores_integridad"]))
        self.assertEqual(resultado["estado_global"], "bloqueado_por_datos_insuficientes")

    def test_piezas_distintas_en_misma_sesion_pueden_tener_diferentes_clases(self):
        filas = [self.fila(1, etiqueta="E0", pieza="M1", sesion="S1"),
                 self.fila(2, etiqueta="E1", pieza="M2", sesion="S1")]
        resultado = self.auditar(filas)
        self.assertFalse(any("etiquetas_contradictorias_pieza" in x
                             for x in resultado["errores_integridad"]))
        self.assertEqual(resultado["productos"]["mango"]["grupos_independientes"], 1)

    def test_estado_pendiente_no_admite_etiqueta_de_calidad(self):
        fila = self.fila(1, estado="pendiente", etiqueta="E1")
        resultado = self.auditar([fila])
        self.assertTrue(any("etiqueta no autorizada" in x
                            for x in resultado["errores_integridad"]))
        self.assertEqual(resultado["productos"]["mango"]["etiquetas_elegibles"], 0)

    def test_no_evaluable_no_admite_etiqueta_de_calidad(self):
        fila = self.fila(1, estado="no_evaluable", etiqueta="E2")
        resultado = self.auditar([fila])
        self.assertTrue(any("etiqueta no autorizada" in x
                            for x in resultado["errores_integridad"]))

    def test_mismo_id_pieza_distinto_lote_no_genera_conflicto_falso(self):
        filas = [self.fila(1, etiqueta="E0", pieza="M1", lote="L1"),
                 self.fila(2, etiqueta="E1", pieza="M1", lote="L2")]
        resultado = self.auditar(filas)
        self.assertFalse(any("etiquetas_contradictorias_pieza" in x
                             for x in resultado["errores_integridad"]))

    def test_csv_consolidado_sigue_bloqueado_sin_etiquetas(self):
        fuente = Path(__file__).parents[1] / "evaluation" / "agrop42" / "AGROP42_revisiones_texto_aprobado_v2.csv"
        if not fuente.is_file():
            self.skipTest("CSV del Incremento 04 no encontrado")
        resultado = auditar_csv(fuente)
        self.assertEqual(resultado["cantidad_registros"], 19)
        self.assertEqual(resultado["productos"]["mango"]["etiquetas_elegibles"], 0)
        self.assertEqual(resultado["productos"]["tomate"]["etiquetas_elegibles"], 0)
        self.assertFalse(resultado["errores_integridad"])
        self.assertIsNone(resultado["metricas_estimadas"])


if __name__ == "__main__":
    unittest.main()
