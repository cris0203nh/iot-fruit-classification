"""AG-036: auditoría offline de umbrales; nunca carga pesos YOLOE."""
from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from vision.evaluation.ag036.evaluar_umbrales_revisados import (
    AuditError, PRED_FIELDS, REVIEW_FIELDS, analyze, main,
)


class AuditoriaUmbralesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.preds = self.root / 'detector.csv'
        self.reviews = self.root / 'revision.csv'
        self.out = self.root / 'informes'
        self.p = [
            self.pred('mango1.jpg','mango','deteccion_lista_para_captura',1,'0.82','si'),
            self.pred('mango2.jpg','mango','confianza_inferior_a_umbral_captura',1,'0.371','si'),
            self.pred('mango3.jpg','mango','confianza_inferior_a_umbral_captura',1,'0.270','si'),
            self.pred('tomate1.jpg','tomate','multiples_candidatos_esperados',2,'0.90','si'),
            self.pred('tomate2.jpg','tomate','deteccion_sin_clase_esperada',0,'','no'),
            self.pred('tomate3.jpg','tomate','sin_deteccion',0,'','no'),
            self.pred('mango4.jpg','mango','sin_poligono_de_segmentacion',1,'0.80','no'),
        ]
        self.r = [self.review(x,decision) for x,decision in zip(self.p[1:],
                   ['Bien localizada','Bien localizada','Bien localizada',
                    'YOLOE falló','YOLOE falló','Duda'])]
        self.dump()

    def pred(self,name,product,state,count,confidence,mask):
        return dict(fuente='captura_proyecto_declarada',producto_candidato=product,
                    grupo_candidato='A',ruta_relativa='carpeta/'+name,
                    sha256_imagen=hashlib.sha256(name.encode()).hexdigest(),
                    estado_deteccion=state,candidatos_producto=str(count),
                    confianza_mejor_coincidencia=confidence,
                    mascara_poligono_disponible=mask,etiqueta_e0_e1_e2='')

    def review(self,p,decision):
        return dict(fuente=p['fuente'],producto=p['producto_candidato'],
                    grupo=p['grupo_candidato'],ruta_relativa=p['ruta_relativa'],
                    sha256_imagen=p['sha256_imagen'],estado_yoloe=p['estado_deteccion'],
                    decision_revisor=decision,observacion_revisor='comentario')

    def dump(self):
        def write(path,rows,fields):
            with path.open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.DictWriter(f,fieldnames=fields)
                w.writeheader();w.writerows(rows)
        write(self.preds,self.p,PRED_FIELDS)
        write(self.reviews,self.r,REVIEW_FIELDS)

    def test_scenarios_and_no_quality_labels(self):
        x=analyze(self.preds,self.reviews,self.out)
        self.assertEqual(x['fotografias'],7)
        self.assertEqual(x['escenarios_candidatos_captura'],{'0.40':1,'0.30':2,'0.25':3})
        self.assertEqual(x['nuevos_candidatos_revisados']['0.30']['revision_bien_localizada'],1)
        self.assertEqual(x['nuevos_candidatos_revisados']['0.25']['revision_bien_localizada'],2)
        self.assertEqual(x['fallos_confirmados_revision'],2)
        self.assertFalse(x['umbral_de_produccion_modificado'])
        self.assertEqual(x['etiquetas_e0_e1_e2'],0)
        self.assertIsNone(x['exactitud_detector'])
        self.assertTrue((self.out/'informe_umbrales.md').is_file())
        with (self.out/'escenarios_97.csv').open(encoding='utf-8-sig') as f:
            self.assertEqual(len(list(csv.DictReader(f))),7)
        with (self.out/'fallos_confirmados.csv').open(encoding='utf-8-sig') as f:
            self.assertEqual(len(list(csv.DictReader(f))),2)

    def test_multiple_candidate_stays_blocked_even_when_human_says_localized(self):
        analyze(self.preds,self.reviews,self.out)
        with (self.out/'escenarios_97.csv').open(encoding='utf-8-sig') as f:
            rows=list(csv.DictReader(f))
        m=next(r for r in rows if r['estado_original']=='multiples_candidatos_esperados')
        self.assertEqual(m['captura_0_25'],'no')
        self.assertEqual(m['motivo_bloqueo'],'multiples_candidatos')

    def test_missing_review_rejected_and_no_outputs(self):
        self.r=self.r[:-1];self.dump()
        with self.assertRaisesRegex(AuditError,'faltan 1'):
            analyze(self.preds,self.reviews,self.out)
        self.assertFalse(self.out.exists())

    def test_overwrite_rejected(self):
        analyze(self.preds,self.reviews,self.out)
        with self.assertRaisesRegex(AuditError,'no se sobrescriben'):
            analyze(self.preds,self.reviews,self.out)

    def test_duplicate_detection_sha_rejected(self):
        self.p.append(dict(self.p[0]));self.dump()
        with self.assertRaisesRegex(AuditError,'repetido'):
            analyze(self.preds,self.reviews,self.out)

    def test_duplicate_revision_rejected(self):
        self.r.append(dict(self.r[0]));self.dump()
        with self.assertRaisesRegex(AuditError,'duplicada'):
            analyze(self.preds,self.reviews,self.out)

    def test_inconsistent_original_status_rejected(self):
        self.p[0]['estado_deteccion']='confianza_inferior_a_umbral_captura';self.dump()
        with self.assertRaisesRegex(AuditError,'incompatible'):
            analyze(self.preds,self.reviews,self.out)

    def test_review_sha_mismatch_rejected(self):
        self.r[0]['sha256_imagen']='a'*64;self.dump()
        with self.assertRaisesRegex(AuditError,'sin correspondencia'):
            analyze(self.preds,self.reviews,self.out)

    def test_review_product_mismatch_rejected(self):
        self.r[0]['producto']='tomate';self.dump()
        with self.assertRaisesRegex(AuditError,'no coincide'):
            analyze(self.preds,self.reviews,self.out)

    def test_review_state_mismatch_rejected(self):
        self.r[0]['estado_yoloe']='sin_deteccion';self.dump()
        with self.assertRaisesRegex(AuditError,'no coincide'):
            analyze(self.preds,self.reviews,self.out)

    def test_invalid_review_choice_rejected(self):
        self.r[0]['decision_revisor']='';self.dump()
        with self.assertRaisesRegex(AuditError,'Decisión'):
            analyze(self.preds,self.reviews,self.out)

    def test_invalid_confidence_rejected(self):
        self.p[1]['confianza_mejor_coincidencia']='NaN';self.dump()
        with self.assertRaisesRegex(AuditError,'Confianza'):
            analyze(self.preds,self.reviews,self.out)

    def test_missing_expected_confidence_rejected(self):
        self.p[1]['confianza_mejor_coincidencia']='';self.dump()
        with self.assertRaisesRegex(AuditError,'sin confianza'):
            analyze(self.preds,self.reviews,self.out)

    def test_traversal_rejected(self):
        self.p[0]['ruta_relativa']='../outside.jpg';self.dump()
        with self.assertRaisesRegex(AuditError,'Ruta de imagen'):
            analyze(self.preds,self.reviews,self.out)

    def test_quality_labels_rejected(self):
        self.p[0]['etiqueta_e0_e1_e2']='E2';self.dump()
        with self.assertRaisesRegex(AuditError,'no deben contener E0'):
            analyze(self.preds,self.reviews,self.out)

    def test_cli_success_and_result_read_back(self):
        self.assertEqual(main(['--resultados',str(self.preds),'--revisiones',str(self.reviews),
                               '--salida-dir',str(self.out)]),0)
        result=json.loads((self.out/'resumen_umbrales.json').read_text(encoding='utf-8'))
        self.assertEqual(result['escenarios_candidatos_captura']['0.25'],3)

    def test_cli_failure_returns_2_without_results(self):
        self.r=[];self.dump()
        # empty review => error
        self.assertEqual(main(['--resultados',str(self.preds),'--revisiones',str(self.reviews),
                               '--salida-dir',str(self.out)]),2)
        self.assertFalse(self.out.exists())

    def test_low_confidence_at_boundary_is_eligible(self):
        self.p[1]['confianza_mejor_coincidencia']='0.30';self.dump()
        report=analyze(self.preds,self.reviews,self.out)
        self.assertEqual(report['escenarios_candidatos_captura']['0.30'],2)

    def test_no_imaginary_reviewer_on_ready_examples(self):
        analyze(self.preds,self.reviews,self.out)
        with (self.out/'escenarios_97.csv').open(encoding='utf-8-sig') as f:
            rows=list(csv.DictReader(f))
        original=next(x for x in rows if x['estado_original']=='deteccion_lista_para_captura')
        self.assertEqual(original['decision_revisor'],'SIN_REVISION')


if __name__=='__main__':
    unittest.main()
