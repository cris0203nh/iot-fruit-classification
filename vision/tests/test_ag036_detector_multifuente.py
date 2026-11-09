"""Pruebas de detección exploratoria con mock, SIN ejecución ni precisión de YOLOE."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from vision.evaluation.ag036.ingestar_dataset_multifuente import INVENTORY_FIELDS,IngestionError
from vision.evaluation.ag036.evaluar_detector_multifuente import evaluate,main

class DetectorMultiFuenteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.images=self.root/'imagenes';self.images.mkdir()
        self.inventory=self.root/'inventario.csv';self.out=self.root/'salida'
        self.rows=[]
        self.put('mango','mango1.png','captura_proyecto_declarada')
        self.put('tomate','tomate1.png','dataset_externo_declarado')
        self.dump()

    def put(self,p,name,source):
        import hashlib
        blob=(f'FAKE DATA {name}').encode()
        (self.images/name).write_bytes(blob)
        d=dict.fromkeys(INVENTORY_FIELDS,'')
        d.update(fuente=source,producto_candidato=p,grupo_candidato='grupo',ruta_relativa=name,
                 sha256_imagen=hashlib.sha256(blob).hexdigest())
        self.rows.append(d)

    def dump(self):
        with self.inventory.open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=INVENTORY_FIELDS)
            writer.writeheader();writer.writerows(self.rows)

    def test_all_photos_evaluated(self):
        def fake(path):return [{'label':'mango fruit' if 'mango' in path.name else 'tomato fruit',
                                'confidence':.9,'box':[1,2,100,100],'mask':True}]
        r=evaluate(self.inventory,self.images,self.out,predictor=fake)
        self.assertEqual(r['fotografias_procesadas'],2)
        self.assertEqual(r['etiquetas_e0_e1_e2_generadas'],0)
        self.assertIsNone(r['medicion_exactitud_clasificador'])
        with (self.out/'resultados_deteccion.csv').open(encoding='utf-8-sig') as f:
            rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),2)
        self.assertTrue(all(x['estado_deteccion']=='deteccion_lista_para_captura' for x in rows))
        self.assertTrue(all(x['etiqueta_e0_e1_e2']=='' for x in rows))

    def test_no_detections(self):
        r=evaluate(self.inventory,self.images,self.out,predictor=lambda _:[])
        with (self.out/'resultados_deteccion.csv').open(encoding='utf-8-sig') as f:
            rows=list(csv.DictReader(f))
        self.assertEqual({x['estado_deteccion'] for x in rows},{'sin_deteccion'})

    def test_confidence_below_threshold(self):
        def fake(_):return [{'label':'mango fruit','confidence':.30,'box':[],'mask':True}]
        evaluate(self.inventory,self.images,self.out,predictor=fake,limit=1)
        with (self.out/'resultados_deteccion.csv').open(encoding='utf-8-sig') as f:
            self.assertEqual(list(csv.DictReader(f))[0]['estado_deteccion'],'confianza_inferior_a_umbral_captura')

    def test_without_polygon(self):
        def fake(_):return [{'label':'mango fruit','confidence':.9,'box':[],'mask':False}]
        evaluate(self.inventory,self.images,self.out,predictor=fake,limit=1)
        with (self.out/'resultados_deteccion.csv').open(encoding='utf-8-sig') as f:
            self.assertEqual(list(csv.DictReader(f))[0]['estado_deteccion'],'sin_poligono_de_segmentacion')

    def test_multiple_expected(self):
        def fake(_):return [{'label':'mango fruit','confidence':.9,'mask':True},
                            {'label':'mango fruit','confidence':.8,'mask':True}]
        evaluate(self.inventory,self.images,self.out,predictor=fake,limit=1)
        with (self.out/'resultados_deteccion.csv').open(encoding='utf-8-sig') as f:
            self.assertEqual(list(csv.DictReader(f))[0]['estado_deteccion'],'multiples_candidatos_esperados')

    def test_wrong_class(self):
        evaluate(self.inventory,self.images,self.out,limit=1,predictor=lambda _: [{'label':'tomato fruit','confidence':.9,'mask':True}])
        with (self.out/'resultados_deteccion.csv').open(encoding='utf-8-sig') as f:
            self.assertEqual(list(csv.DictReader(f))[0]['estado_deteccion'],'deteccion_sin_clase_esperada')

    def test_tamper_image_blocked(self):
        (self.images/'mango1.png').write_bytes(b'changed')
        with self.assertRaisesRegex(IngestionError,'SHA256 alterado'):
            evaluate(self.inventory,self.images,self.out,predictor=lambda _:[])
        self.assertFalse(self.out.exists())

    def test_invalid_path_traversal(self):
        self.rows[0]['ruta_relativa']='../fuera.png';self.dump()
        with self.assertRaisesRegex(IngestionError,'Ruta inválida'):
            evaluate(self.inventory,self.images,self.out,predictor=lambda _:[])

    def test_no_overwrite(self):
        evaluate(self.inventory,self.images,self.out,predictor=lambda _:[])
        with self.assertRaisesRegex(IngestionError,'No sobrescribir'):
            evaluate(self.inventory,self.images,self.out,predictor=lambda _:[])

    def test_limit_processes_one(self):
        r=evaluate(self.inventory,self.images,self.out,predictor=lambda _:[],limit=1)
        self.assertEqual(r['fotografias_procesadas'],1)

    def test_reject_negative_limit(self):
        with self.assertRaisesRegex(IngestionError,'límite'):
            evaluate(self.inventory,self.images,self.out,predictor=lambda _:[],limit=-1)


if __name__=='__main__':unittest.main()
