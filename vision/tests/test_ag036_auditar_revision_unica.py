"""Pruebas sinteticas del cierre de una revision; no incluyen etiquetas humanas reales."""
import csv
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from PIL import Image
from vision.evaluation.ag036.auditar_etiquetado import UNIVERSE_COLS, REVIEW_COLS, AuditError
from vision.evaluation.ag036.auditar_revision_unica import audit_single, _observations

class SingleReviewerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.imgs=root/'imagenes';self.imgs.mkdir()
        self.universe=root/'universo.csv'
        self.return_zip=root/'A.zip'
        self.output=root/'auditoria'
        self.records=[];self.reviews=[]
        for product,lot,piece,rubric,variety in [('mango','L01','P01','kent-ext-v0.4','Kent'),('tomate','L02','P02','tomato-ext-v0.2','Rojo')]:
            image=self.imgs/f'{piece}.png';Image.new('RGB',(36,36),'orange' if product == 'mango' else 'red').save(image)
            self.records.append({'producto':product,'variedad_declarada':variety,'lote_id':lot,'pieza_id':piece,
             'sesion_id':f'S_{piece}','imagen_relativa':image.name,'sha256_imagen':hashlib.sha256(image.read_bytes()).hexdigest(),
             'rubrica_version':rubric,'seleccion_doble':'si','criterio_seleccion':'piloto'})
            self.reviews.append({'producto':product,'lote_id':lot,'pieza_id':piece,'revisor_id':'REV_A1',
             'fecha_revision_iso':'2026-11-09T11:05:00-05:00','rubrica_version':rubric,'estado_revision':'etiquetada',
             'etiqueta_e0_e1_e2':'E0','justificacion':'sin defecto externo visible','criterios_rxx':'',
             'ubicacion_evidencia':'','soporte_relativo':f'{piece}.txt'})
        self.write()

    def write(self, omit_support=None, files=None):
        with self.universe.open('w',newline='',encoding='utf-8-sig') as stream:
            writer=csv.DictWriter(stream,fieldnames=UNIVERSE_COLS);writer.writeheader();writer.writerows(self.records)
        buffer=io.StringIO(newline='');w=csv.DictWriter(buffer,fieldnames=REVIEW_COLS);w.writeheader();w.writerows(self.reviews)
        with zipfile.ZipFile(self.return_zip,'w') as z:
            z.writestr('revision_A.csv',buffer.getvalue().encode('utf-8-sig'))
            for row in self.reviews:
                if row['soporte_relativo'] != omit_support:
                    z.writestr('soportes/'+row['soporte_relativo'],b'evidencia')
            for name, blob in (files or []): z.writestr(name,blob)

    def test_real_one_reviewer_coverage_without_kappa(self):
        report=audit_single(self.universe,self.imgs,self.return_zip,self.output)
        self.assertEqual(report['piezas_etiquetadas_por_A'],2)
        self.assertEqual(report['cobertura_de_A_sobre_subconjunto'],1)
        self.assertIsNone(report['kappa_entre_humanos'])
        self.assertFalse(report['cierre_del_criterio_original_doble_concordancia'])
        self.assertTrue((self.output/'informe_revision_unica.md').is_file())

    def test_missing_support_rejected(self):
        self.write(omit_support='P01.txt')
        with self.assertRaises(AuditError):audit_single(self.universe,self.imgs,self.return_zip,self.output)
        self.assertFalse(self.output.exists())

    def test_bad_label_rejected(self):
        self.reviews[0]['etiqueta_e0_e1_e2']='E7';self.write()
        with self.assertRaises(AuditError):audit_single(self.universe,self.imgs,self.return_zip,self.output)

    def test_wrong_reviewer_identity_rejected(self):
        self.reviews[1]['revisor_id']='REV_OTRO';self.write()
        with self.assertRaises(AuditError):audit_single(self.universe,self.imgs,self.return_zip,self.output)

    def test_piece_set_not_identical_rejected(self):
        self.reviews.pop();self.write()
        with self.assertRaises(AuditError):audit_single(self.universe,self.imgs,self.return_zip,self.output)

    def test_no_overwrite(self):
        audit_single(self.universe,self.imgs,self.return_zip,self.output)
        with self.assertRaises(AuditError):audit_single(self.universe,self.imgs,self.return_zip,self.output)

    def test_path_traversal_blocked(self):
        self.write(files=[('soportes/../../evil.txt','bad')])
        with self.assertRaises(AuditError):audit_single(self.universe,self.imgs,self.return_zip,self.output)

    def test_duplicate_zip_names_blocked(self):
        self.write(files=[('soportes/P01.txt','duplicate')])
        with self.assertRaises(AuditError):audit_single(self.universe,self.imgs,self.return_zip,self.output)

    def test_e0_defect_text_flag_never_changes_label(self):
        self.reviews[0]['justificacion']='mango normal con inicios de manchas negras'
        observations=_observations(self.reviews)
        self.assertIn('E0_con_mencion',observations[0]['banderas_de_revision'])
        self.assertEqual(observations[0]['etiqueta_original'],'E0')
        self.assertEqual(observations[0]['etiqueta_modificada'],'no')

    def test_invalid_date_rejected(self):
        self.reviews[0]['fecha_revision_iso']='2026-11-09T11:05:00';self.write()
        with self.assertRaises(AuditError):audit_single(self.universe,self.imgs,self.return_zip,self.output)

if __name__=='__main__':unittest.main()
