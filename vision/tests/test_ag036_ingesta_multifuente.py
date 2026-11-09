"""Pruebas de integridad de inventario; imágenes sintéticas, no datos agronómicos."""
import csv
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image
from vision.evaluation.ag036.ingestar_dataset_multifuente import IngestionError, ingest, main

ROOT='AgroScan_Imagenes_Revisadas/'
MANGO='01_ZIP_Capturas_reales/Mango_variedad_pendiente/Candidato_M01_rojo/'
TOMATE='01_ZIP_Capturas_reales/Tomate_tipo_pendiente/Candidato_T02/'
KENT='02_Datasets_externos/Mango_Kent_COFiLAB_dos_vistas/KENT_EXT_01/'
CHERRY='02_Datasets_externos/Tomate_Cherry_Rojo_Fruits360/Objeto_Cherry_Red_2/'


def photo(rgb=(255,0,0),size=(300,300)):
    b=io.BytesIO()
    Image.new('RGB',size,rgb).save(b,format='PNG')
    return b.getvalue()


class IngestaMultiFuenteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.z=self.root/'fuentes.zip'
        self.out=self.root/'salida'
        self.data=[
            (ROOT+MANGO+'E-000024_a.png',photo((200,20,20))),
            (ROOT+MANGO+'E-000033_b.png',photo((210,20,20))),
            (ROOT+TOMATE+'E-000037_c.png',photo((220,20,20))),
            (ROOT+KENT+'Mango_01_A.png',photo((230,30,30))),
            (ROOT+CHERRY+'Serie_01.png',photo((240,20,20),(200,300))),
        ]
        self.rewrite()

    def rewrite(self):
        with zipfile.ZipFile(self.z,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for name,blob in self.data:
                z.writestr(name,blob)

    def read(self,name):
        with (self.out/name).open('r',encoding='utf-8-sig',newline='') as f:
            return list(csv.DictReader(f))

    def test_inventory_covers_all_images_and_separates_sources(self):
        result=ingest(self.z,self.out)
        self.assertEqual(result['fotografias_total'],5)
        self.assertEqual(result['grupos_de_carpetas_candidatos'],4)
        self.assertEqual(result['sha256_imagenes_unicos'],5)
        rows=self.read('inventario_multifuente.csv')
        self.assertEqual(len(rows),5)
        self.assertEqual(sum(r['fuente']=='captura_proyecto_declarada' for r in rows),3)
        self.assertEqual(sum(r['fuente']=='dataset_externo_declarado' for r in rows),2)

    def test_does_not_guess_external_variety_or_e0(self):
        ingest(self.z,self.out)
        rows=self.read('inventario_multifuente.csv')
        self.assertTrue(all(not r['etiqueta_e0_e1_e2'] for r in rows))
        self.assertTrue(all(r['identidad_pieza_confirmada']=='no' for r in rows))
        self.assertTrue(all(r['licencia_y_procedencia_verificadas']=='no' for r in rows))
        self.assertEqual(self.read('universo_AG036_borrador.csv')[0]['seleccion_doble'],'no')
        self.assertTrue(all(not r['pieza_id'] for r in self.read('universo_AG036_borrador.csv')))
        self.assertEqual(result:=json.loads((self.out/'resumen_multifuente.json').read_text(encoding='utf-8'))['etiquetas_e0_e1_e2_acreditadas'],0)

    def test_identical_path_deduplicated_rejected(self):
        self.data.append(self.data[0]); self.rewrite()
        with self.assertRaisesRegex(IngestionError,'Ruta duplicada'):
            ingest(self.z,self.out)

    def test_identical_image_different_paths_recorded_not_ignored(self):
        self.data.append((ROOT+TOMATE+'E-000038_copy.png',self.data[0][1]))
        self.rewrite()
        r=ingest(self.z,self.out)
        self.assertEqual(r['fotografias_total'],6)
        self.assertEqual(r['sha256_duplicados'],1)

    def test_zip_traversal_rejected_without_creating_output(self):
        self.data.append((ROOT+'../escape.png',photo()))
        self.rewrite()
        with self.assertRaisesRegex(IngestionError,'insegura'):
            ingest(self.z,self.out)
        self.assertFalse(self.out.exists())

    def test_unknown_source_rejected(self):
        self.data=[('otro/tipo/grupo/test.png',photo())]
        self.rewrite()
        with self.assertRaisesRegex(IngestionError,'Procedencia no reconocida'):
            ingest(self.z,self.out)

    def test_unsupported_file_rejected(self):
        self.data.append((ROOT+'archivo.exe',b'x'))
        self.rewrite()
        with self.assertRaisesRegex(IngestionError,'no fotográfico'):
            ingest(self.z,self.out)

    def test_corrupt_image_rejected(self):
        self.data[0]=(self.data[0][0],b'not a picture')
        self.rewrite()
        with self.assertRaisesRegex(IngestionError,'corrupta'):
            ingest(self.z,self.out)

    def test_no_overwrite(self):
        ingest(self.z,self.out)
        with self.assertRaisesRegex(IngestionError,'ya existe'):
            ingest(self.z,self.out)

    def test_hash_and_original_bytes_preserved(self):
        ingest(self.z,self.out)
        row=self.read('inventario_multifuente.csv')[0]
        data=(self.out/'imagenes'/row['ruta_relativa']).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(),row['sha256_imagen'])

    def test_folder_group_not_auto_pieces(self):
        r=ingest(self.z,self.out)
        self.assertEqual(r['piezas_fisicas_independientes_acreditadas'],0)
        groups=self.read('grupos_candidatos.csv')
        first=next(x for x in groups if x['grupo_candidato']=='Candidato_M01_rojo')
        self.assertEqual(first['fotografias'],'2')
        self.assertEqual(first['codigos_captura_distintos'],'2')
        self.assertEqual(first['pieza_fisica_confirmada'],'no')

    def test_low_res_marked_not_skipped(self):
        r=ingest(self.z,self.out)
        self.assertEqual(r['imagenes_con_dimension_menor_224'],1)
        self.assertEqual(len(self.read('inventario_multifuente.csv')),5)

    def test_cli_success(self):
        self.assertEqual(main(['--zip',str(self.z),'--salida-dir',str(self.out)]),0)

    def test_cli_rejects_no_input(self):
        self.assertEqual(main(['--zip',str(self.root/'missing.zip'),'--salida-dir',str(self.out)]),2)


if __name__=='__main__':unittest.main()
