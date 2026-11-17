"""Incremento 08: pruebas sintéticas, no etiquetas reales E0/E1/E2."""
import csv
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from PIL import Image

from vision.evaluation.ag036.ingestar_dataset_multifuente import INVENTORY_FIELDS, IngestionError
from vision.evaluation.ag036.auditar_etiquetado import load_universe
from vision.evaluation.ag036.construir_universo_v2 import build
from vision.evaluation.ag036.preparar_paquetes_revision import prepare
from vision.evaluation.ag036.formulario_revision_offline import render_form

class UniversoV2Tests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.base=Path(self.t.name);self.root=self.base/'imagenes';self.root.mkdir()
        self.inventory=self.base/'inventario.csv';self.output=self.base/'universe'
        self.rows=[]
        self.add('02_Datasets_externos/Mango_Kent_COFiLAB_dos_vistas/KENT_EXT_01/Mango_01_A.JPG','mango','KENT_EXT_01','dataset_externo_declarado')
        self.add('02_Datasets_externos/Mango_Kent_COFiLAB_dos_vistas/KENT_EXT_01/Mango_01_B.JPG','mango','KENT_EXT_01','dataset_externo_declarado')
        self.add('02_Datasets_externos/Tomate_Rojo_Hohenheim_3_vistas/TOM_EXT_01_Tc_01/Tc_0101_D3.JPG','tomate','TOM_EXT_01_Tc_01','dataset_externo_declarado')
        self.add('01_ZIP_Capturas_reales/Mango_variedad/Candidato_M01_rojo/E-000024_a.jpg','mango','Candidato_M01_rojo','captura_proyecto_declarada')
        self.add('01_ZIP_Capturas_reales/Tomate/Candidato_T01/E-000027_a.jpg','tomate','Candidato_T01','captura_proyecto_declarada')
        self.dump()

    def add(self,relative,product,group,source):
        dest=self.root/relative;dest.parent.mkdir(parents=True,exist_ok=True)
        Image.new('RGB',(64,64),(len(self.rows)*37%255,80,120)).save(dest)
        r=dict.fromkeys(INVENTORY_FIELDS,'')
        r.update(fuente=source,producto_candidato=product,grupo_candidato=group,
                 ruta_relativa=relative,sha256_imagen=hashlib.sha256(dest.read_bytes()).hexdigest())
        self.rows.append(r)

    def dump(self):
        with self.inventory.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=INVENTORY_FIELDS);w.writeheader();w.writerows(self.rows)

    def test_build_selected_external_only(self):
        summary=build(self.inventory,self.root,self.output)
        self.assertEqual((summary['fotografias'],summary['grupos_totales']), (5,4))
        self.assertEqual(summary['grupos_seleccionados_declarados'],2)
        self.assertEqual(summary['fotografias_seleccionadas'],3)
        with (self.output/'universo_AG036_v2.csv').open(encoding='utf-8-sig',newline='') as f:
            rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),5)
        self.assertEqual([r['seleccion_doble'] for r in rows].count('si'),3)
        self.assertEqual({r['variedad_declarada'] for r in rows if r['producto']=='mango' and r['seleccion_doble']=='si'}, {'Kent'})
        self.assertEqual([r['variedad_declarada'] for r in rows if r['producto']=='mango' and r['seleccion_doble']=='no'], ['variedad_no_acreditada'])
        self.assertTrue(all(not r['etiqueta_e0_e1_e2'] for r in self.rows))
        universe,info=load_universe(self.output/'universo_AG036_v2.csv',self.root)
        self.assertEqual(info['piezas'],4)
        self.assertEqual(universe[('mango','EXT_COFILAB','KENT_EXT_01')]['vistas'],2)
        self.assertFalse(summary['entrenamiento_autorizado'])
        self.assertFalse(summary['licencias_acreditadas'] if 'licencias_acreditadas' in summary else summary['procedencia_y_licencias_acreditadas'])

    def test_compatible_with_blind_packager(self):
        summary=build(self.inventory,self.root,self.output)
        folder=self.base/'paquetes'
        result=prepare(self.output/'universo_AG036_v2.csv',self.root,folder)
        self.assertEqual((result['piezas'],result['vistas']),(2,3))
        for slot in ('A','B'):
            with zipfile.ZipFile(folder/f'AG036_Revisor_{slot}.zip') as z:
                self.assertIsNone(z.testzip())
                html=z.read(f'formulario_{slot}.html').decode('utf-8')
                self.assertIn('Exportar devolución '+slot,html)
                self.assertIn('Pendiente',html)
                self.assertIn('soportes/',html)
                self.assertIn('previsualizaciones/',html)
                self.assertEqual(len([n for n in z.namelist() if n.startswith('previsualizaciones/')]),3)
                self.assertNotIn('formulario_'+('B' if slot=='A' else 'A')+'.html',z.namelist())
                record=list(csv.DictReader(z.read(f'revision_{slot}.csv').decode('utf-8-sig').splitlines()))
                self.assertEqual(len(record),2)
                self.assertTrue(all(not r['etiqueta_e0_e1_e2'] for r in record))
        act=json.loads((folder/'AG036_acta_preparacion.json').read_text(encoding='utf-8'))
        self.assertEqual(act['piezas_seleccionadas'],2)
        self.assertFalse(act['cierre_total_AG036_acreditado'])

    def test_reject_tampered(self):
        (self.root/self.rows[0]['ruta_relativa']).write_bytes(b'tampered')
        with self.assertRaisesRegex(IngestionError,'SHA256'):
            build(self.inventory,self.root,self.output)
        self.assertFalse(self.output.exists())

    def test_reject_same_image_twice(self):
        a=self.rows[0]
        self.rows[1]['sha256_imagen']=a['sha256_imagen']
        (self.root/self.rows[1]['ruta_relativa']).write_bytes((self.root/a['ruta_relativa']).read_bytes());self.dump()
        with self.assertRaisesRegex(IngestionError,'duplicada'):
            build(self.inventory,self.root,self.output)

    def test_reject_mismatch_product(self):
        self.rows[0]['producto_candidato']='tomate';self.dump()
        with self.assertRaisesRegex(IngestionError,'contradictorios'):
            build(self.inventory,self.root,self.output)

    def test_reject_bad_group(self):
        self.rows[0]['grupo_candidato']='Otro';self.dump()
        with self.assertRaisesRegex(IngestionError,'grupo'):
            build(self.inventory,self.root,self.output)

    def test_reject_unknown_source(self):
        self.rows[0]['fuente']='inventada';self.dump()
        with self.assertRaisesRegex(IngestionError,'contradictorios'):
            build(self.inventory,self.root,self.output)

    def test_reject_escape(self):
        self.rows[0]['ruta_relativa']='../../evil.jpg';self.dump()
        with self.assertRaisesRegex(IngestionError,'estructura v2'):
            build(self.inventory,self.root,self.output)

    def test_no_overwrite(self):
        build(self.inventory,self.root,self.output)
        with self.assertRaisesRegex(IngestionError,'existente'):
            build(self.inventory,self.root,self.output)

    def test_renderer_no_injection(self):
        p=[dict(producto='mango',lote_id='LOTE',pieza_id='X<svg/onload=alert(1)>',rubrica_version='kent-ext-v0.4',imagenes=[dict(imagen_relativa='file.jpg')])]
        html=render_form(p,'A').decode('utf-8')
        self.assertNotIn('X<svg',html)
        self.assertIn('\\u003csvg',html)
        self.assertIn('const SLOT = \'A\';',html)
        self.assertNotIn('value="E0" selected',html)
        with self.assertRaises(ValueError):render_form(p,'X')

    def test_empty_inventory(self):
        self.rows=[];self.dump()
        with self.assertRaisesRegex(IngestionError,'vacío'):
            build(self.inventory,self.root,self.output)

if __name__=='__main__':unittest.main()
