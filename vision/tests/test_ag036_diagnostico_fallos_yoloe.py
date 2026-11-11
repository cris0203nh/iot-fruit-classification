"""AG-036 incremento 07: reproducibilidad sin dependencias de torch ni YOLOE."""
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from vision.evaluation.ag036.diagnosticar_fallos_yoloe import (
    DiagnosticoError, classify, evaluate, main,
)

DETECT_FIELDS = [
    'fuente','producto_candidato','grupo_candidato','ruta_relativa',
    'sha256_imagen','estado_deteccion',
]
FAIL_FIELDS = [
    'producto','fuente','grupo','ruta_relativa','sha256_imagen',
    'estado_original','decision_revisor','observacion_revisor',
]


class DiagnosticoYoloETests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.images = self.root / 'imagenes'
        self.images.mkdir()
        self.detector = self.root / 'detector.csv'
        self.failures = self.root / 'fallos.csv'
        self.out = self.root / 'informe'
        self.detections, self.fails = [], []
        for i in range(10):
            product = 'mango' if i < 8 else 'tomate'
            state = 'deteccion_sin_clase_esperada' if i < 7 else 'sin_deteccion'
            self.add(i, product, state, is_fail=True)
        for i in range(10, 14):
            product = 'mango' if i % 2 else 'tomate'
            self.add(i, product, 'deteccion_lista_para_captura', is_fail=False)
        self.dump()

    def add(self, i, product, state, is_fail):
        route = f'{product}/grupo_{i:02d}/f_{i}.jpg'
        path = self.images / route
        path.parent.mkdir(parents=True,exist_ok=True)
        content = f'imagen de prueba {i}'.encode('utf-8')
        path.write_bytes(content)
        sha = hashlib.sha256(content).hexdigest()
        source = 'captura_proyecto_declarada' if i % 2 else 'dataset_externo_declarado'
        self.detections.append(dict(fuente=source,producto_candidato=product,
            grupo_candidato=f'grupo_{i:02d}',ruta_relativa=route,
            sha256_imagen=sha,estado_deteccion=state))
        if is_fail:
            self.fails.append(dict(producto=product,fuente=source,
                grupo=f'grupo_{i:02d}',ruta_relativa=route,
                sha256_imagen=sha,estado_original=state,
                decision_revisor='YOLOE falló',observacion_revisor='fruta visible'))

    def dump(self):
        for path, fields, records in ((self.detector,DETECT_FIELDS,self.detections),
                                      (self.failures,FAIL_FIELDS,self.fails)):
            with path.open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.DictWriter(f,fieldnames=fields)
                w.writeheader();w.writerows(records)

    def predictor(self, path, size):
        product=path.parts[-3]
        idx=int(path.stem.split('_')[-1])
        expected='mango fruit' if product=='mango' else 'tomato fruit'
        other='tomato fruit' if product=='mango' else 'mango fruit'
        if idx<10:
            if size==512:
                return [{'label':other,'confidence':.78,'mask':True,'box':[1,2,3,4]}] if idx<7 else []
            if size==640 and idx in (0,8):
                return [{'label':expected,'confidence':.75,'mask':True,'box':[1,2,3,4]}]
            if size==768 and idx in (0,1,8):
                return [{'label':expected,'confidence':.75,'mask':True,'box':[1,2,3,4]}]
            return []
        if size==768 and idx==10:
            return []
        return [{'label':expected,'confidence':.9,'mask':True,'box':[1,2,3,4]}]

    def test_01_clase_incorrecta(self):
        result=classify([{'label':'tomato fruit','confidence':.92,'mask':True}],'mango')
        self.assertEqual(result['estado_nuevo'],'deteccion_sin_clase_esperada')
        self.assertEqual(result['clase_top'],'tomato fruit')

    def test_02_sin_deteccion(self):
        self.assertEqual(classify([],'tomate')['estado_nuevo'],'sin_deteccion')

    def test_03_multiple_sin_aceptar(self):
        result=classify([{'label':'mango','confidence':.99,'mask':True},
                         {'label':'mango','confidence':.75,'mask':True}],'mango')
        self.assertEqual(result['estado_nuevo'],'multiples_candidatos_esperados')

    def test_04_confianza_baja(self):
        result=classify([{'label':'mango','confidence':.38,'mask':True}],'mango')
        self.assertEqual(result['estado_nuevo'],'confianza_inferior_a_umbral_captura')

    def test_05_sin_mascara(self):
        result=classify([{'label':'tomato','confidence':.88,'mask':False}],'tomate')
        self.assertEqual(result['estado_nuevo'],'sin_poligono_de_segmentacion')

    def test_06_aceptacion_normal(self):
        result=classify([{'label':'tomato','confidence':.9,'mask':True,'box':[0,1,2,3]}],'tomate')
        self.assertEqual(result['estado_nuevo'],'deteccion_lista_para_captura')
        self.assertEqual(json.loads(result['caja_producto']),[0,1,2,3])

    def test_07_no_confianza_fuera_de_rango(self):
        with self.assertRaises(DiagnosticoError):
            classify([{'label':'mango','confidence':1.2}],'mango')

    def test_08_preparar_sin_inferencia(self):
        report=evaluate(self.detector,self.failures,self.images,self.out,mode='preparar',controls=3)
        self.assertEqual(report['fallos_humanamente_confirmados'],10)
        self.assertEqual(report['fallos_por_producto'],{'mango':8,'tomate':2})
        self.assertEqual(report['controles_automaticos_sin_revision_humana'],3)
        self.assertFalse((self.out/'resultados_variantes.csv').exists())
        with (self.out/'casos_seleccionados.csv').open(encoding='utf-8-sig') as f:
            rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),13)
        self.assertEqual(sum(row['tipo_caso']=='fallo_confirmado' for row in rows),10)

    def test_09_inferencia_pareada_y_regresiones(self):
        report=evaluate(self.detector,self.failures,self.images,self.out,
                        mode='inferir',predictor=self.predictor,controls=4)
        self.assertEqual(report['comparacion_por_resolucion'][0]['fallos_candidatos_recuperados'],0)
        self.assertEqual(report['comparacion_por_resolucion'][0]['desacuerdos_con_estado_original_en_512'],0)
        self.assertEqual(report['comparacion_por_resolucion'][1]['fallos_candidatos_recuperados'],2)
        self.assertEqual(report['comparacion_por_resolucion'][2]['fallos_candidatos_recuperados'],3)
        self.assertEqual(report['comparacion_por_resolucion'][2]['regresiones_operativas_controles'],1)
        self.assertFalse(report['despliegue_autorizado'])
        with (self.out/'resultados_variantes.csv').open(encoding='utf-8-sig') as f:
            rows=list(csv.DictReader(f))
        self.assertEqual(len(rows),42)
        self.assertTrue(all(row['revision_visual_requerida']=='si' for row in rows))
        self.assertTrue((self.out/'detecciones_completas.jsonl').exists())

    def test_10_no_sobrescribir(self):
        evaluate(self.detector,self.failures,self.images,self.out,mode='preparar',controls=1)
        with self.assertRaisesRegex(DiagnosticoError,'existe'):
            evaluate(self.detector,self.failures,self.images,self.out,mode='preparar',controls=1)

    def test_11_hash_alterado_no_genera_salida(self):
        path=self.images/self.detections[0]['ruta_relativa']
        path.write_bytes(b'alterado')
        with self.assertRaisesRegex(DiagnosticoError,'SHA256'):
            evaluate(self.detector,self.failures,self.images,self.out,mode='preparar',controls=1)
        self.assertFalse(self.out.exists())

    def test_12_fallo_no_revision_humana(self):
        self.fails[0]['decision_revisor']='Bien localizada'
        self.dump()
        with self.assertRaisesRegex(DiagnosticoError,'revision'):
            evaluate(self.detector,self.failures,self.images,self.out,mode='preparar',controls=1)

    def test_13_fallo_no_coincide_estado(self):
        self.fails[0]['estado_original']='sin_deteccion'
        self.dump()
        with self.assertRaisesRegex(DiagnosticoError,'revision'):
            evaluate(self.detector,self.failures,self.images,self.out,mode='preparar',controls=1)

    def test_14_ruta_insegura(self):
        self.detections[0]['ruta_relativa']='../escape.jpg'
        self.dump()
        with self.assertRaisesRegex(DiagnosticoError,'insegura'):
            evaluate(self.detector,self.failures,self.images,self.out,mode='preparar',controls=1)

    def test_15_no_permitir_controles_excesivos(self):
        with self.assertRaisesRegex(DiagnosticoError,'controles'):
            evaluate(self.detector,self.failures,self.images,self.out,mode='preparar',controls=100)

    def test_16_sin_controles(self):
        report=evaluate(self.detector,self.failures,self.images,self.out,mode='preparar',controls=0)
        self.assertEqual(report['controles_automaticos_sin_revision_humana'],0)

    def test_17_resoluciones_invalidas(self):
        with self.assertRaisesRegex(DiagnosticoError,'Resoluciones'):
            evaluate(self.detector,self.failures,self.images,self.out,mode='preparar',controls=1,sizes=(640,768))

    def test_18_esperar_10_fallos(self):
        self.fails.pop()
        self.dump()
        with self.assertRaisesRegex(DiagnosticoError,'10 fallos'):
            evaluate(self.detector,self.failures,self.images,self.out,mode='preparar',controls=1)

    def test_19_error_cli_controlado(self):
        code=main(['--resultados',str(self.detector),'--fallos',str(self.root/'inexistente.csv'),
                   '--raiz-imagenes',str(self.images),'--salida-dir',str(self.out),'--modo','preparar'])
        self.assertEqual(code,2)
        self.assertFalse(self.out.exists())


if __name__=='__main__': unittest.main()
