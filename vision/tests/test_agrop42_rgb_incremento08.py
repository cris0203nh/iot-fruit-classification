"""Pruebas de integración AGROP-42 Incremento 08 (sin usar datos del usuario)."""
from __future__ import annotations
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw
from vision.evaluation.agrop42.evaluar_rgb_incremento08 import (
    IngestaInvalida, _relative_path, evaluate, verify,
)


class RGBIncremento08Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "ingesta"
        (self.root / "originales").mkdir(parents=True)
        self.output = Path(self.temp.name) / "derivado"
        self.rows = []

    def add_image(self, product="mango", piece="MANGO_01", view="1", size=(160,160), tint=(250,55,30)):
        image = Image.new("RGB",size,(235,235,235))
        draw = ImageDraw.Draw(image)
        draw.ellipse((30,30,size[0]-30,size[1]-30),fill=tint)
        temp = self.root / "tmp.jpg"
        image.save(temp,format="JPEG",quality=95)
        content=temp.read_bytes()
        digest=hashlib.sha256(content).hexdigest()
        filename=f"originales/{digest}.jpg"
        (self.root / filename).write_bytes(content)
        temp.unlink()
        self.rows.append({
            "archivo":f"{product}/{piece}/vista_{view}.jpg",
            "archivo_importado":filename,
            "id_ejemplar":piece,"vista":view,"producto":product,
            "sha256":digest,"sha256_comprobado":digest,
            "ancho_comprobado":str(size[0]),"alto_comprobado":str(size[1]),
            "es_captura_propia":"no","clasificacion_e0_e1_e2":"",
        })
        return digest

    def save_inventory(self):
        with (self.root/"inventario_externo.csv").open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(self.rows[0]));w.writeheader();w.writerows(self.rows)
        (self.root/"control_externo.json").write_text(json.dumps({
            "fotografias":len(self.rows),
            "procedencia":"externa; no captura propia del proyecto",
            "entrenamiento_autorizado":False,
        }),encoding="utf-8")

    def test_dos_productos_y_mascaras_sin_etiquetas(self):
        self.add_image()
        self.add_image("tomate","TOMATE_01","1",tint=(220,45,35))
        self.save_inventory()
        report=evaluate(self.root,self.output,previews_per_piece=0)
        self.assertEqual(report["fotografias_procesadas"],2)
        self.assertFalse(report["entrenamiento_autorizado"])
        self.assertIsNone(report["precision_o_metricas_de_clasificacion"])
        self.assertEqual(report["conteo_por_producto"]["mango"]["fotos_con_mascara_candidata"],1)
        self.assertEqual(report["conteo_por_producto"]["tomate"]["fotos_con_mascara_candidata"],1)
        self.assertEqual(verify(self.output)["estado"],"integridad_resultados_verificada")

    def test_dos_vistas_misma_pieza_no_suman_dos_frutos(self):
        self.add_image(view="1")
        self.add_image(view="2",tint=(240,80,20))
        self.save_inventory()
        report=evaluate(self.root,self.output,previews_per_piece=0)
        self.assertEqual(report["identificadores_de_fuente"],1)
        self.assertEqual(report["conteo_por_producto"]["mango"]["grupos_independientes_verificados"],0)

    def test_mascara_rgb_no_usa_el_fondo_gris(self):
        self.add_image()
        self.save_inventory()
        evaluate(self.root,self.output,previews_per_piece=0)
        with (self.output/"resultados_por_vista.csv").open(encoding="utf-8-sig",newline="") as f:
            row=next(csv.DictReader(f))
        rgb=json.loads(row["mediana_rgb_mascara"])
        self.assertGreater(rgb[0],rgb[1]+100)
        self.assertGreater(rgb[0],rgb[2]+100)

    def test_100_px_no_finge_calidad_suficiente(self):
        self.add_image(size=(100,100))
        self.save_inventory()
        report=evaluate(self.root,self.output,previews_per_piece=0)
        self.assertEqual(report["conteo_por_producto"]["mango"]["fotografias_menor_128px"],1)

    def test_previews_separadas_sin_mutar_original(self):
        sha=self.add_image()
        self.save_inventory()
        before=(self.root/"originales"/f"{sha}.jpg").read_bytes()
        report=evaluate(self.root,self.output,previews_per_piece=1)
        after=(self.root/"originales"/f"{sha}.jpg").read_bytes()
        self.assertEqual(before,after)
        self.assertEqual(len([name for name in report["sha256_salidas"] if name.endswith(".png")]),2)

    def test_tamper_imagen_rechazado(self):
        sha=self.add_image()
        self.save_inventory()
        (self.root/"originales"/f"{sha}.jpg").write_bytes(b"corrupto")
        with self.assertRaises(IngestaInvalida):evaluate(self.root,self.output,0)
        self.assertFalse(self.output.exists())

    def test_sha_duplicado_rechazado(self):
        self.add_image()
        self.rows.append(dict(self.rows[0],vista="2"))
        self.save_inventory()
        with self.assertRaises(IngestaInvalida):evaluate(self.root,self.output,0)

    def test_ruta_windows_y_traversal_rechazadas(self):
        for raw in ("C:/temp/foto.jpg", "originales/../foto.jpg", "originales\\foto.jpg", "/originales/foto.jpg"):
            with self.subTest(raw=raw),self.assertRaises(IngestaInvalida):_relative_path(raw)

    def test_procedencia_mal_declarada_rechazada(self):
        self.add_image()
        self.save_inventory()
        info=self.root/"control_externo.json"
        data=json.loads(info.read_text());data["entrenamiento_autorizado"]=True
        info.write_text(json.dumps(data))
        with self.assertRaises(IngestaInvalida):evaluate(self.root,self.output,0)

    def test_etiqueta_no_justificada_rechazada(self):
        self.add_image()
        self.rows[0]["clasificacion_e0_e1_e2"]="E0"
        self.save_inventory()
        with self.assertRaises(IngestaInvalida):evaluate(self.root,self.output,0)

    def test_no_sobrescribir_salida(self):
        self.add_image();self.save_inventory();self.output.mkdir()
        with self.assertRaises(FileExistsError):evaluate(self.root,self.output,0)

    def test_salida_dentro_de_ingesta_rechazada(self):
        self.add_image();self.save_inventory()
        with self.assertRaises(IngestaInvalida):evaluate(self.root,self.root/"nuevo",0)

    def test_verificacion_detecta_cambio_csv(self):
        self.add_image();self.save_inventory();evaluate(self.root,self.output,0)
        with (self.output/"resultados_por_vista.csv").open("a") as f:f.write("ALTERADO")
        with self.assertRaises(IngestaInvalida):verify(self.output)

    def test_diferente_producto_mismo_id_rechazado(self):
        self.add_image("mango","PIEZA_1","1")
        self.add_image("tomate","PIEZA_1","2",tint=(225,60,30))
        self.save_inventory()
        with self.assertRaises(IngestaInvalida):evaluate(self.root,self.output,0)

    def test_salida_sin_originales_falla(self):
        self.add_image();self.save_inventory()
        for p in (self.root/"originales").iterdir():p.unlink()
        with self.assertRaises(IngestaInvalida):evaluate(self.root,self.output,0)

    def test_resolucion_del_inventario_no_miente(self):
        self.add_image();self.rows[0]["ancho_comprobado"]="1000";self.save_inventory()
        with self.assertRaises(IngestaInvalida):evaluate(self.root,self.output,0)

if __name__=="__main__":unittest.main()
