"""Incremento 07: pruebas de importación segura de datos externos (sin frutas reales)."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

from vision.evaluation.agrop42.auditar_revisiones import auditar_csv
from vision.evaluation.agrop42.ingestar_fuentes_externas import (
    COLUMNAS_FUENTE, ErrorFuentesExternas, ingresar_zip, validar_zip,
    verificar_salida, main,
)


def jpg(color: str) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (240, 240), color).save(output, "JPEG")
    return output.getvalue()


def paquete(base: Path, *, alterar=None, extra=None, sube_ruta=None) -> Path:
    """Genera datos mínimos sin etiquetas, con vistas múltiples por pieza."""
    registros, fotos = [], {}
    for producto, carpeta, pid in (("mango", "mangos", "MANGO_01"), ("tomate", "tomates", "TOMATE_01")):
        for n in (1, 2, 3):
            ruta = f"{carpeta}/{pid}/vista_{n:02d}.jpg"
            blob = jpg(("red", "orange", "yellow")[n-1] if producto == "mango" else ("green", "blue", "purple")[n-1])
            fotos[ruta] = blob
            registros.append({
                "archivo": ruta, "carpeta": carpeta, "id_ejemplar": pid,
                "vista": str(n), "grupo_original": f"FUENTE_{pid}",
                "estado_fuente": "estado declarado", "observacion_visual": "sin clase comercial",
                "archivo_original": f"source/{pid}/frame{n}.jpg",
                "fuente": "https://example.org/source", "licencia": "https://example.org/license",
                "resolucion_px": "240x240", "sha256": hashlib.sha256(blob).hexdigest(),
            })
    if alterar:
        alterar(registros, fotos)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNAS_FUENTE, lineterminator="\n")
    writer.writeheader(); writer.writerows(registros)
    path = base / "datos.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as f:
        f.writestr("trazabilidad.csv", buffer.getvalue())
        f.writestr("LEEME.md", "Insumos de prueba sintéticos")
        for ruta, blob in fotos.items():
            f.writestr(ruta, blob)
        if extra:
            f.writestr(sube_ruta or "extra.jpg", jpg("cyan"))
    return path


class FuentesExternasTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def test_inventario_y_agrupacion_sin_etiquetas(self):
        ruta = paquete(self.base)
        filas, report = validar_zip(ruta)
        self.assertEqual(len(filas), 6)
        self.assertEqual(report["ejemplares_declarados"], {"mango": 1, "tomate": 1})
        self.assertEqual(report["sha256_correctos"], 6)
        self.assertFalse(report["entrenamiento_autorizado"])

    def test_no_atribuir_variedad_kent(self):
        filas, _ = validar_zip(paquete(self.base))
        self.assertTrue(all("no_Kent" in f["observacion_tecnica"] for f in filas if f["producto"] == "mango"))

    def test_importa_originales_externos_y_sin_sesiones_falsas(self):
        ruta = paquete(self.base)
        out = self.base / "importada"
        ingresar_zip(ruta, out)
        self.assertTrue(out.joinpath("control_externo.json").exists())
        with (out / "revisiones_pendientes.csv").open(encoding="utf-8", newline="") as f:
            filas = list(csv.DictReader(f))
        self.assertEqual(len(filas), 6)
        for fila in filas:
            self.assertEqual(fila["estado_revision"], "pendiente")
            self.assertEqual(fila["etiqueta_visual"], "")
            self.assertEqual(fila["pieza_id"], "")
            self.assertEqual(fila["sesion_id"], "")
            self.assertEqual(fila["revisor_id"], "")
        audit = auditar_csv(out / "revisiones_pendientes.csv")
        self.assertFalse(audit["evaluacion_ejecutada"])
        self.assertEqual(audit["estado_global"], "bloqueado_por_datos_insuficientes")
        self.assertFalse(audit["errores_integridad"])

    def test_verifica_sin_reclasificar(self):
        out = self.base / "importada"
        ingresar_zip(paquete(self.base), out)
        reporte = verificar_salida(out)
        self.assertEqual(reporte["fotografias"], 6)
        self.assertEqual(reporte["estado"], "integridad_verificada")
        self.assertFalse(reporte["entrenamiento_autorizado"])

    def test_detecta_alteracion_tras_importar(self):
        out = self.base / "importada"
        ingresar_zip(paquete(self.base), out)
        item = json.loads((out / "control_externo.json").read_text(encoding="utf-8"))["originales"][0]
        (out / item["archivo"]).write_bytes(b"corrupto")
        with self.assertRaisesRegex(ErrorFuentesExternas, "alterada"):
            verificar_salida(out)

    def test_no_sobrescribe_ingesta(self):
        out = self.base / "importada"
        paquete_src = paquete(self.base)
        ingresar_zip(paquete_src, out)
        with self.assertRaisesRegex(ErrorFuentesExternas, "ya existe"):
            ingresar_zip(paquete_src, out)

    def test_detecta_sha_alterado(self):
        def cambio(regs, _): regs[0]["sha256"] = "0"*64
        with self.assertRaisesRegex(ErrorFuentesExternas, "SHA256"):
            validar_zip(paquete(self.base, alterar=cambio))

    def test_detecta_duplicado_de_sha(self):
        def cambio(regs, fotos):
            fotos[regs[1]["archivo"]] = fotos[regs[0]["archivo"]]
            regs[1]["sha256"] = regs[0]["sha256"]
        with self.assertRaisesRegex(ErrorFuentesExternas, "repetida"):
            validar_zip(paquete(self.base, alterar=cambio))

    def test_rechaza_ruta_zip_slip(self):
        with self.assertRaisesRegex(ErrorFuentesExternas, "insegura"):
            validar_zip(paquete(self.base, extra=True, sube_ruta="../escape.jpg"))

    def test_rechaza_archivos_no_inventariados(self):
        with self.assertRaisesRegex(ErrorFuentesExternas, "sin entrada"):
            validar_zip(paquete(self.base, extra=True))

    def test_rechaza_resolucion_falsa(self):
        def cambio(regs, _): regs[0]["resolucion_px"] = "400x200"
        with self.assertRaisesRegex(ErrorFuentesExternas, "resolución"):
            validar_zip(paquete(self.base, alterar=cambio))

    def test_rechaza_grupos_contradictorios(self):
        def cambio(regs, _): regs[1]["grupo_original"] = "OTRA_FRUTA"
        with self.assertRaisesRegex(ErrorFuentesExternas, "grupo original"):
            validar_zip(paquete(self.base, alterar=cambio))

    def test_rechaza_vistas_incompletas(self):
        def cambio(regs, fotos):
            borrar = regs.pop(1)
            del fotos[borrar["archivo"]]
        with self.assertRaisesRegex(ErrorFuentesExternas, "vistas incompletas"):
            validar_zip(paquete(self.base, alterar=cambio))

    def test_rechaza_archivo_corrupto(self):
        def cambio(regs, fotos):
            foto = regs[0]["archivo"]
            fotos[foto] = b"no es un jpeg"
            regs[0]["sha256"] = hashlib.sha256(fotos[foto]).hexdigest()
            regs[0]["resolucion_px"] = "240x240"
        with self.assertRaisesRegex(ErrorFuentesExternas, "fotografía inválida"):
            validar_zip(paquete(self.base, alterar=cambio))

    def test_no_requiere_fechar_sesion_inexistente(self):
        out = self.base / "importada"
        ingresar_zip(paquete(self.base), out)
        with (out / "inventario_externo.csv").open(encoding="utf-8", newline="") as f:
            rr = list(csv.DictReader(f))
        self.assertTrue(all(x["es_captura_propia"] == "no" for x in rr))
        self.assertTrue(all(x["revision_visual"] == "pendiente" for x in rr))

    def test_detecta_csv_formula_inyectada(self):
        def cambio(regs, _): regs[0]["observacion_visual"] = "=2+2"
        with self.assertRaisesRegex(ErrorFuentesExternas, "fórmula"):
            validar_zip(paquete(self.base, alterar=cambio))

    def test_detecta_revisiones_alteradas_en_control_original(self):
        out = self.base / "importada"
        ingresar_zip(paquete(self.base), out)
        with (out / "revisiones_pendientes.csv").open("a", encoding="utf-8") as f:
            f.write("\n")
        with self.assertRaisesRegex(ErrorFuentesExternas, "alterada"):
            verificar_salida(out)

    def test_cli_valida_sin_producir_salida(self):
        self.assertEqual(main(["validar", "--zip", str(paquete(self.base))]), 0)
        self.assertEqual(sorted(x.name for x in self.base.iterdir()), ["datos.zip"])

if __name__ == "__main__":
    unittest.main()
