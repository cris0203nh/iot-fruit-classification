"""AG-037: tests de integridad y reproducibilidad del informe retrospectivo."""
import csv
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from vision.evaluation.ag037.evaluar_umbrales_cierre import evaluate, write_results


def detector(confidence='', count='0', state='sin_deteccion', sha='a', product='mango', mask='no'):
    return {
        'fuente': 'fuente-de-prueba', 'producto_candidato': product,
        'grupo_candidato': 'GRUPO-01', 'ruta_relativa': f'{sha}.jpg',
        'sha256_imagen': sha*64, 'estado_deteccion': state,
        'candidatos_producto': count, 'confianza_mejor_coincidencia': confidence,
        'mascara_poligono_disponible': mask,
    }


def manual(sha, decision='Bien localizada', product='mango'):
    return {'sha256_imagen': sha*64, 'producto': product, 'decision_revisor': decision}


class AG037CierreExperimentalTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            detector('0.60','1','deteccion_lista_para_captura','a',mask='si'),
            detector('0.34','1','confianza_inferior_a_umbral_captura','b',mask='si'),
            detector('0.27','1','confianza_inferior_a_umbral_captura','c',mask='si'),
            detector('0.75','2','multiples_candidatos_esperados','d',mask='si'),
            detector('', '0','sin_deteccion','e'),
        ]
        self.reviews = [manual('b'), manual('c'), manual('d'), manual('e','YOLOE falló')]

    def test_coverage_thresholds(self):
        report, _ = evaluate(self.rows, self.reviews)
        self.assertEqual([s['admitidas'] for s in report['escenarios']], [1,2,3])
        self.assertEqual([s['retenidas'] for s in report['escenarios']], [4,3,2])
        self.assertEqual([s['admitidas_revisadas_bien_localizadas'] for s in report['escenarios']], [0,1,2])
        self.assertEqual([s['retenidas_revisadas_bien_localizadas'] for s in report['escenarios']], [3,2,1])

    def test_unknown_admissions_not_presented_as_accuracy(self):
        report, _ = evaluate(self.rows, self.reviews)
        self.assertFalse(report['exactitud_detector_estimable'])
        self.assertIsNone(report['escenarios'][0]['tasa_falsas_aceptaciones_global'])
        self.assertIsNone(report['escenarios'][1]['precision_del_detector'])
        self.assertEqual(report['imagenes_sin_revision'], 1)

    def test_multiple_candidates_blocked_at_all_thresholds(self):
        report, rows = evaluate(self.rows,self.reviews)
        x = rows[3]
        self.assertEqual(x['candidatos_producto'],2)
        self.assertEqual([s['retenidas_revisadas_bien_localizadas'] for s in report['escenarios']][-1],1)

    def test_duplicate_detector_sha_rejected(self):
        with self.assertRaisesRegex(ValueError,'duplicado'):
            evaluate(self.rows + [self.rows[0]], self.reviews)

    def test_duplicate_manual_sha_rejected(self):
        with self.assertRaisesRegex(ValueError,'duplicado'):
            evaluate(self.rows, self.reviews + [self.reviews[0]])

    def test_manual_not_in_detector_rejected(self):
        with self.assertRaisesRegex(ValueError,'no vinculable'):
            evaluate(self.rows, self.reviews + [manual('f')])

    def test_manual_on_accepted_rejected(self):
        with self.assertRaisesRegex(ValueError,'solo rechazos'):
            evaluate(self.rows, self.reviews + [manual('a')])

    def test_state_inconsistent_with_gate_rejected(self):
        corrupted = deepcopy(self.rows)
        corrupted[0]['estado_deteccion']='confianza_inferior_a_umbral_captura'
        with self.assertRaisesRegex(ValueError,'no coincide'):
            evaluate(corrupted, self.reviews)

    def test_invalid_confidence_rejected(self):
        corrupted = deepcopy(self.rows)
        corrupted[1]['confianza_mejor_coincidencia']='NaN'
        with self.assertRaisesRegex(ValueError,'fuera de rango'):
            evaluate(corrupted,self.reviews)

    def test_product_mismatch_rejected(self):
        corrupted = deepcopy(self.reviews)
        corrupted[1]['producto']='tomate'
        with self.assertRaisesRegex(ValueError,'discordante'):
            evaluate(self.rows,corrupted)

    def test_write_outputs_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            detection=root/'deteccion.csv'
            revisions=root/'revision.csv'
            for path,records in [(detection,self.rows),(revisions,self.reviews)]:
                with path.open('w',encoding='utf-8-sig',newline='') as f:
                    w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
            result=write_results(detection,revisions,root/'output')
            self.assertEqual(result['imagenes'],5)
            self.assertEqual(json.loads((root/'output/resumen_ag037.json').read_text(encoding='utf-8'))['imagenes'],5)
            with (root/'output/casos_trazables.csv').open(encoding='utf-8-sig') as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 5)
            with self.assertRaisesRegex(ValueError,'existe'):
                write_results(detection,revisions,root/'output')

    def test_output_not_created_for_invalid_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);detection=root/'a.csv';revisions=root/'b.csv'
            detection.write_text('wrong,fields\n1,2\n',encoding='utf-8')
            revisions.write_text('wrong,fields\n1,2\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'columnas'):
                write_results(detection,revisions,root/'output')
            self.assertFalse((root/'output').exists())


if __name__=='__main__':
    unittest.main()
