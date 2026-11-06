"""Pruebas del paquete AG-034 Incremento 13; no simulan evidencia física real."""
import csv
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vision.evaluation.agrop42 import validacion_hardware_ag034 as hw


class TestValidacionHardwareAG034(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.form = self.base / "formulario"
        hw.plantilla(self.form)

    def rows(self):
        return hw._read_rows(self.form)

    def write(self, rows):
        (self.form / "AG034_registro_pruebas.csv").write_bytes(hw._csv_bytes(rows))

    def passed(self, row, evidence="evidencias/acta.txt"):
        row.update(estado="aprobada", equipo_id="PC-01", responsable="REVISOR-01",
                   fecha_iso="2026-11-05T21:20:00-05:00", evidencia_relativa=evidence,
                   criterio_predefinido="Criterio documentado antes del ensayo",
                   observaciones="Prueba documentada: contenido de test, no evidencia real")
        if row["prueba_id"] == "VIS-03":
            row.update(limite_ms="2000", resultado_ms="900", limite_mib="1024", resultado_mib="300")
        (self.form / "evidencias" / "acta.txt").write_text("fixture de prueba", encoding="utf-8")

    def test_plantilla_no_acredita_hardware(self):
        result = hw.auditar_registros(self.form)
        self.assertEqual(len(result["pruebas"]), 7)
        self.assertFalse(result["pruebas_fisicas_declaradas_completas"])
        self.assertFalse(result["cierre_total_AG034_acreditado"])

    def test_plantilla_no_se_sobrescribe(self):
        with self.assertRaises(FileExistsError):
            hw.plantilla(self.form)

    def test_ids_exactos_no_se_pueden_modificar(self):
        rows = self.rows(); rows[0]["prueba_id"] = "VIS-99"; self.write(rows)
        with self.assertRaisesRegex(ValueError, "IDs"):
            hw.auditar_registros(self.form)

    def test_pruebas_obligatorias_no_admiten_no_aplica(self):
        rows = self.rows(); rows[0]["estado"] = "no_aplica"; self.write(rows)
        self.assertTrue(any("no_aplica" in v for v in hw.auditar_registros(self.form)["errores"]))

    def test_esp32_complementario_no_sustituye_pc(self):
        rows = self.rows()
        for row in rows:
            if row["alcance"] == "complementaria":
                row.update(estado="no_aplica", equipo_id="PC-01", responsable="REV-1",
                           fecha_iso="2026-11-05T21:20:00-05:00", observaciones="No hay ESP32 físico")
        self.write(rows)
        result = hw.auditar_registros(self.form)
        self.assertFalse(result["pruebas_fisicas_declaradas_completas"])
        self.assertFalse(result["errores"])

    def test_no_acepta_aprobada_sin_evidencia(self):
        rows = self.rows(); rows[0]["estado"] = "aprobada"; self.write(rows)
        self.assertTrue(hw.auditar_registros(self.form)["errores"])

    def test_no_acepta_fecha_sin_timezone(self):
        rows = self.rows(); self.passed(rows[0]); rows[0]["fecha_iso"] = "2026-11-05T21:20:00"; self.write(rows)
        self.assertTrue(any("zona horaria" in e for e in hw.auditar_registros(self.form)["errores"]))

    def test_no_acepta_recorrido_fuera_de_evidencias(self):
        for name in ("../secret.txt", "evidencias/../../fuera.txt", "C:/Windows/win.ini", "evidencias\\x.txt"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                hw._evidence_file(self.form, name)

    def test_no_acepta_symlink_fuera(self):
        outside = self.base / "exterior.txt"; outside.write_text("dato", encoding="utf-8")
        sym = self.form / "evidencias" / "atrapa.txt"
        try:
            sym.symlink_to(outside)
        except OSError:
            self.skipTest("Sistema no admite enlace simbólico")
        with self.assertRaisesRegex(ValueError, "fuera"):
            hw._evidence_file(self.form, "evidencias/atrapa.txt")

    def test_metrica_sobre_limite_no_aprueba(self):
        rows = self.rows(); self.passed(rows[2]); rows[2]["resultado_ms"] = "2001"; self.write(rows)
        self.assertTrue(any("excede" in e for e in hw.auditar_registros(self.form)["errores"]))

    def test_memoria_sobre_limite_no_aprueba(self):
        rows = self.rows(); self.passed(rows[2]); rows[2]["resultado_mib"] = "3000"; self.write(rows)
        self.assertTrue(any("excede" in e for e in hw.auditar_registros(self.form)["errores"]))

    def test_no_acepta_nan_ni_infinito(self):
        for val in ("nan", "inf", "0", "-1"):
            with self.subTest(val=val), self.assertRaises(ValueError):
                hw._positive_float(val, "limite")

    def test_no_finge_validacion_de_defectos(self):
        rows = self.rows()
        for row in rows[:4]:
            self.passed(row)
        self.write(rows)
        result = hw.auditar_registros(self.form)
        self.assertTrue(result["pruebas_fisicas_declaradas_completas"])
        self.assertFalse(result["hardware_pc_validado_independientemente"])
        self.assertFalse(result["etiquetas_e0_e1_e2_acreditadas"])
        self.assertFalse(result["cierre_total_AG034_acreditado"])

    def test_no_aprueba_sin_criterio_previsto(self):
        rows = self.rows(); self.passed(rows[0]); rows[0]["criterio_predefinido"] = ""; self.write(rows)
        self.assertTrue(any("criterio" in e for e in hw.auditar_registros(self.form)["errores"]))

    def test_rechaza_evidencia_vacia(self):
        empty = self.form / "evidencias" / "empty.txt"; empty.touch()
        with self.assertRaisesRegex(ValueError, "vacío"):
            hw._evidence_file(self.form, "evidencias/empty.txt")

    def test_auditar_y_verificar_pendientes(self):
        out = self.base / "salida"
        result = hw.auditar(self.form, out)
        self.assertEqual(result["estado"], "pruebas_fisicas_pendientes_o_no_conformes")
        self.assertEqual(hw.verificar(out, self.form)["estado"], "integridad_documental_verificada")

    def test_rechaza_auditoria_que_sobrescribe(self):
        out = self.base / "salida"; hw.auditar(self.form, out)
        with self.assertRaises(ValueError):
            hw.auditar(self.form, out)

    def test_rechaza_auditoria_en_carpeta_fuente(self):
        with self.assertRaises(ValueError):
            hw.auditar(self.form, self.form / "salida")

    def test_detecta_informe_modificado(self):
        out = self.base / "salida"; hw.auditar(self.form, out)
        with (out / "AG034_informe_hardware.md").open("a", encoding="utf-8") as f:
            f.write("Alterado")
        with self.assertRaisesRegex(ValueError, "Integridad alterada"):
            hw.verificar(out)

    def test_detecta_csv_modificado_posterior(self):
        out = self.base / "salida"; hw.auditar(self.form, out)
        p = self.form / "AG034_registro_pruebas.csv"
        with p.open("ab") as f:
            f.write(b"\n")
        with self.assertRaisesRegex(ValueError, "CSV editable cambió"):
            hw.verificar(out, self.form)

    def test_detecta_archivo_evidencia_modificado(self):
        rows = self.rows(); self.passed(rows[0]); self.write(rows)
        out = self.base / "salida"; hw.auditar(self.form, out)
        with (self.form / "evidencias" / "acta.txt").open("a", encoding="utf-8") as f:
            f.write("CAMBIO")
        with self.assertRaisesRegex(ValueError, "evidencia alterado"):
            hw.verificar(out, self.form)

    def test_diagnostico_rechaza_url_externa(self):
        for url in ("https://example.org/api/health", "http://example.org/api/health",
                    "http://127.0.0.1:8000/api/health?secret=1", "http://user:pw@localhost/api/health"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                hw.diagnosticar(url, self.base / "diag.json")

    def test_diagnostico_api_inaccesible_no_valida_hardware(self):
        with patch.object(hw.urllib.request, "urlopen", side_effect=hw.urllib.error.URLError("offline")):
            result = hw.diagnosticar("http://127.0.0.1:8000/api/health", self.base / "diag.json")
        self.assertFalse(result["api_ok"])
        data = json.loads((self.base / "diag.json").read_text("utf-8"))
        self.assertFalse(data["esp32_fisico_verificado"])
        self.assertFalse(data["cierre_total_AG034_acreditado"])

    def test_diagnostico_no_sobrescribe(self):
        with patch.object(hw.urllib.request, "urlopen", side_effect=hw.urllib.error.URLError("offline")):
            hw.diagnosticar("http://localhost:8000/api/health", self.base / "diag.json")
            with self.assertRaises(FileExistsError):
                hw.diagnosticar("http://localhost:8000/api/health", self.base / "diag.json")

    def test_perfil_malformado_no_es_hardware(self):
        profile = self.base / "bad.json"; profile.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Perfil experimental ajeno"):
            hw.diagnosticar("http://localhost:8000/api/health", self.base / "diag.json", profile)

    def test_cli_preparar_y_verificar(self):
        folder = self.base / "via_cli"
        self.assertEqual(hw.main(["plantilla", "--salida", str(folder)]), 0)
        out = self.base / "resultado"
        self.assertEqual(hw.main(["auditar", "--carpeta", str(folder), "--salida", str(out)]), 0)
        self.assertEqual(hw.main(["verificar", "--salida", str(out), "--carpeta", str(folder)]), 0)

    def test_validacion_multivista_no_se_infiere_de_planilla(self):
        out = self.base / "resultado"
        hw.auditar(self.form, out)
        data = json.loads((out / "AG034_auditoria_hardware.json").read_text("utf-8"))
        self.assertNotIn("resultados_e0_e1_e2", data)
        self.assertFalse(data["etiquetas_e0_e1_e2_acreditadas"])


if __name__ == "__main__":
    unittest.main()
