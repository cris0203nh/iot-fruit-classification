"""AGROP-42 Incremento 06 — todas las imágenes y filas de prueba son artificiales."""
import csv
import json
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from vision.evaluation.agrop42.auditar_revisiones import auditar_csv
from vision.evaluation.agrop42.registrar_capturas import (
    COLUMNAS_ENTRADA, ErrorCapturas, ingresar_capturas, main,
    validar_capturas, verificar_ingesta,
)


class IngestaCapturasTests(unittest.TestCase):
    def setUp(self):
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        self.raiz = Path(carpeta.name)
        self.entrada = self.raiz / "entrada"
        self.entrada.mkdir()
        self.csv = self.raiz / "capturas.csv"
        self.salida = self.raiz / "ingesta"

    def foto(self, nombre, color=(120, 80, 20), *, formato="JPEG", size=(640, 480)):
        ruta = self.entrada / nombre
        ruta.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, color=color).save(ruta, format=formato)
        return ruta

    def fila(self, idx=1, *, nombre="mango1.jpg", producto="mango", vista="frontal",
             pieza="M01", sesion="S01", lote="L01", operador="OP01", dispositivo="CAM01"):
        return dict(
            registro_id=f"CAP-{idx:04d}", producto=producto,
            variedad_declarada="Kent" if producto == "mango" else "",
            lote_id=lote, pieza_id=pieza, sesion_id=sesion, dispositivo_id=dispositivo,
            operador_id=operador, capturado_en="2026-11-05T12:30:00-05:00",
            vista=vista, archivo_relativo=nombre, procedencia="captura_propia",
            autorizacion_ref="REG-AUTORIZACION-01",
            referencia_identidad_pieza="Etiqueta física CAP-01 visible en control local",
            referencia_identidad_sesion="Bitácora de sesión guardada por responsable",
            observaciones="Foto de captura para ensayo técnico",
        )

    def crear_csv(self, *filas):
        with self.csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNAS_ENTRADA)
            w.writeheader()
            w.writerows(filas)

    def caso_correcto(self):
        self.foto("mango1.jpg")
        self.foto("mango2.jpg", (150, 75, 35))
        self.crear_csv(self.fila(), self.fila(2, nombre="mango2.jpg", vista="posterior"))

    def assert_invalido(self, fila, texto):
        self.crear_csv(fila)
        registros, errores = validar_capturas(self.csv, self.entrada)
        self.assertEqual(registros, [])
        self.assertTrue(any(texto in e for e in errores), errores)
        with self.assertRaises(ErrorCapturas):
            ingresar_capturas(self.csv, self.entrada, self.salida)
        self.assertFalse(self.salida.exists())

    def test_importa_dos_vistas_de_misma_pieza_sin_dos_grupos(self):
        self.caso_correcto()
        resumen = ingresar_capturas(self.csv, self.entrada, self.salida)
        self.assertEqual(resumen["cantidad_fotografias"], 2)
        self.assertEqual(resumen["piezas_declaradas"], 1)
        self.assertEqual(resumen["sesiones_declaradas"], 1)
        self.assertEqual(resumen["clases_etiquetadas"], 0)
        self.assertFalse(resumen["entrenamiento_autorizado"])
        self.assertEqual(verificar_ingesta(self.salida)["fotografias"], 2)
        informe = auditar_csv(self.salida / "revisiones_pendientes.csv")
        self.assertEqual(informe["productos"]["mango"]["etiquetas_elegibles"], 0)
        self.assertEqual(informe["productos"]["mango"]["grupos_independientes"], 0)
        self.assertEqual(informe["estado_global"], "bloqueado_por_datos_insuficientes")
        self.assertFalse(informe["errores_integridad"])

    def test_copia_bit_a_bit_y_preserva_original(self):
        self.caso_correcto()
        original = (self.entrada / "mango1.jpg").read_bytes()
        ingresar_capturas(self.csv, self.entrada, self.salida)
        control = json.loads((self.salida / "control_ingesta.json").read_text(encoding="utf-8"))
        self.assertEqual((self.salida / control["archivos"][0]["archivo"]).read_bytes(), original)
        self.assertEqual((self.entrada / "mango1.jpg").read_bytes(), original)

    def test_referencias_no_se_convierten_en_evidencias_confirmadas(self):
        self.caso_correcto()
        ingresar_capturas(self.csv, self.entrada, self.salida)
        with (self.salida / "revisiones_pendientes.csv").open(newline="", encoding="utf-8") as f:
            filas = list(csv.DictReader(f))
        for f in filas:
            for campo in ("calidad_confirmada", "cobertura_confirmada", "pieza_confirmada",
                          "sesion_confirmada", "evidencia_pieza", "evidencia_sesion",
                          "etiqueta_visual", "justificacion_etiqueta", "revisor_id"):
                self.assertEqual(f[campo], "", campo)
            self.assertEqual(f["estado_revision"], "pendiente")

    def test_verificar_detecta_original_modificado(self):
        self.caso_correcto()
        r = ingresar_capturas(self.csv, self.entrada, self.salida)
        imagen = self.salida / r["archivos"][0]["archivo"]
        imagen.write_bytes(b"CAMBIADO")
        with self.assertRaisesRegex(ErrorCapturas, "alterada"):
            verificar_ingesta(self.salida)

    def test_verificar_detecta_inventario_modificado(self):
        self.caso_correcto()
        ingresar_capturas(self.csv, self.entrada, self.salida)
        with (self.salida / "inventario_capturas.csv").open("a", encoding="utf-8") as f:
            f.write("CAMBIO\n")
        with self.assertRaisesRegex(ErrorCapturas, "alterado"):
            verificar_ingesta(self.salida)

    def test_no_sobrescribe_ingesta_existente(self):
        self.caso_correcto()
        ingresar_capturas(self.csv, self.entrada, self.salida)
        with self.assertRaisesRegex(ErrorCapturas, "ya existe"):
            ingresar_capturas(self.csv, self.entrada, self.salida)

    def test_foto_externa_no_puede_declararse_externa(self):
        self.foto("mango1.jpg")
        f = self.fila()
        f["procedencia"] = "externo_original"
        self.assert_invalido(f, "solo se admiten capturas propias")

    def test_falta_autorizacion_rechazada(self):
        self.foto("mango1.jpg")
        f = self.fila()
        f["autorizacion_ref"] = ""
        self.assert_invalido(f, "falta referencia documental")

    def test_referencia_identidad_faltante_rechazada(self):
        self.foto("mango1.jpg")
        f = self.fila()
        f["referencia_identidad_pieza"] = ""
        self.assert_invalido(f, "faltan referencias")

    def test_imagen_invalida_rechazada(self):
        (self.entrada / "mango1.jpg").write_bytes(b"esto no es jpg")
        self.assert_invalido(self.fila(), "imagen ilegible/corrupta")

    def test_imagen_extension_falsa_rechazada(self):
        self.foto("mango1.jpg", formato="PNG")
        self.assert_invalido(self.fila(), "extensión correcta")

    def test_fecha_sin_zona_rechazada(self):
        self.foto("mango1.jpg")
        f = self.fila()
        f["capturado_en"] = "2026-11-05T12:30:00"
        self.assert_invalido(f, "zona horaria")

    def test_ruta_traversal_rechazada(self):
        self.foto("mango1.jpg")
        f = self.fila()
        f["archivo_relativo"] = "../mango1.jpg"
        self.assert_invalido(f, "ruta relativa")

    def test_ruta_windows_rechazada(self):
        self.foto("mango1.jpg")
        f = self.fila()
        f["archivo_relativo"] = r"C:\fotos\imagen.jpg"
        self.assert_invalido(f, "ruta relativa")

    def test_sha_duplicado_rechazado_aunque_rutas_distintas(self):
        self.foto("mango1.jpg")
        (self.entrada / "mango2.jpg").write_bytes((self.entrada / "mango1.jpg").read_bytes())
        self.crear_csv(self.fila(), self.fila(2, nombre="mango2.jpg", vista="posterior"))
        filas, errores = validar_capturas(self.csv, self.entrada)
        self.assertEqual(len(filas), 1)
        self.assertTrue(any("SHA-256" in x for x in errores))
        with self.assertRaises(ErrorCapturas):
            ingresar_capturas(self.csv, self.entrada, self.salida)
        self.assertFalse(self.salida.exists())

    def test_misma_pieza_en_dos_lotes_rechazada(self):
        self.foto("mango1.jpg")
        self.foto("mango2.jpg", (153, 80, 40))
        self.crear_csv(self.fila(), self.fila(2, nombre="mango2.jpg", lote="L02", vista="posterior"))
        _, errores = validar_capturas(self.csv, self.entrada)
        self.assertTrue(any("reutilizado entre lotes" in x for x in errores))

    def test_sesion_mismo_id_con_otro_dispositivo_rechazada(self):
        self.foto("mango1.jpg")
        self.foto("mango2.jpg", (153, 80, 40))
        self.crear_csv(self.fila(), self.fila(2, nombre="mango2.jpg", vista="posterior", dispositivo="CAM02"))
        _, errores = validar_capturas(self.csv, self.entrada)
        self.assertTrue(any("sesion_id reutilizado" in x for x in errores))

    def test_misma_vista_pieza_y_sesion_rechazada(self):
        self.foto("mango1.jpg")
        self.foto("mango2.jpg", (153, 80, 40))
        self.crear_csv(self.fila(), self.fila(2, nombre="mango2.jpg"))
        _, errores = validar_capturas(self.csv, self.entrada)
        self.assertTrue(any("misma vista repetida" in x for x in errores))

    def test_no_permite_salida_dentro_de_originales(self):
        self.caso_correcto()
        with self.assertRaisesRegex(ErrorCapturas, "fuera del directorio"):
            ingresar_capturas(self.csv, self.entrada, self.entrada / "salida")

    def test_imagen_pequena_solo_dispara_alerta_no_clase(self):
        self.foto("mango1.jpg", size=(320, 240))
        self.crear_csv(self.fila())
        r = ingresar_capturas(self.csv, self.entrada, self.salida)
        self.assertEqual(r["alertas_resolucion"], ["CAP-0001"])
        self.assertEqual(r["clases_etiquetadas"], 0)

    def test_tomate_variedad_vacia_admitida_sin_inferencias(self):
        self.foto("tomate1.png", formato="PNG")
        self.crear_csv(self.fila(nombre="tomate1.png", producto="tomate", pieza="T001"))
        r = ingresar_capturas(self.csv, self.entrada, self.salida)
        self.assertEqual(r["productos"], {"tomate": 1})
        self.assertEqual(r["estado_revision"], "pendiente")

    def test_plantilla_cli_no_sobrescribe(self):
        self.assertEqual(main(["plantilla", "--csv", str(self.csv)]), 0)
        self.assertEqual(main(["plantilla", "--csv", str(self.csv)]), 2)
        with self.csv.open(newline="", encoding="utf-8") as f:
            self.assertEqual(next(csv.reader(f)), list(COLUMNAS_ENTRADA))

    def test_prevalidar_cli_sin_copiar(self):
        self.caso_correcto()
        self.assertEqual(main(["prevalidar", "--csv", str(self.csv), "--entrada", str(self.entrada)]), 0)
        self.assertFalse(self.salida.exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "requiere enlaces simbólicos")
    def test_symlink_fuera_de_directorio_rechazado(self):
        foto_externa = self.raiz / "externa.jpg"
        Image.new("RGB", (640, 480), (66, 30, 30)).save(foto_externa)
        try:
            os.symlink(foto_externa, self.entrada / "mango1.jpg")
        except (OSError, NotImplementedError):
            self.skipTest("No se permiten enlaces simbólicos en este equipo")
        self.assert_invalido(self.fila(), "enlace simbólico")


if __name__ == "__main__":
    unittest.main()
