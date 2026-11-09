"""Evidencia de AG-038 en API real aislada, sin ESP32 ni datos productivos."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from audit.ag038_cierre import audit


class AG038CierreAuditoriaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='ag038-test-cierre-')
        cls.resultdir = Path(cls.tmp.name) / 'salida'
        cls.result = audit(cls.resultdir)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_report_is_explicitly_simulated(self):
        self.assertEqual(self.result['resultado'],'aprobado')
        self.assertFalse(self.result['hardware_esp32_utilizado'])
        self.assertFalse(self.result['fotografias_reales_utilizadas'])
        self.assertFalse(self.result['base_de_datos_productiva_utilizada'])

    def test_report_contains_real_generated_evidence(self):
        report=json.loads((self.resultdir/'resumen_auditoria.json').read_text(encoding='utf-8'))
        self.assertEqual(report['cantidad_decisiones_almacenadas'],7)
        self.assertEqual(report['cantidad_evaluaciones_simuladas'],2)
        self.assertGreaterEqual(report['cantidad_validaciones'],10)

    def test_csv_is_consistent_and_complete(self):
        with (self.resultdir/'bitacora_decisiones.csv').open(encoding='utf-8-sig',newline='') as f:
            records=list(csv.DictReader(f))
        self.assertEqual(len(records),7)
        self.assertEqual({x['actor_id'] for x in records},{'ag038_sim_revisor'})
        self.assertEqual({x['action'] for x in records},
                         {'initial_label','confirm','correct','no_evaluable'})
        self.assertTrue(all(x['image_sha256']==self.result['sha256_fotografia_sintetica'] for x in records))
        self.assertTrue(all(x['reason'] and x['performed_at'] for x in records))

    def test_confirm_correct_and_history(self):
        with (self.resultdir/'bitacora_decisiones.csv').open(encoding='utf-8-sig',newline='') as f:
            records=list(csv.DictReader(f))
        a=[r for r in records if r['original_value']=='E1']
        self.assertEqual([r['action'] for r in a],['confirm','correct','confirm','confirm'])
        self.assertEqual([(r['previous_value'],r['new_value']) for r in a[:3]],
                         [('E1','E1'),('E1','E2'),('E2','E2')])
        self.assertEqual(a[0]['review_id'] != a[1]['review_id'],True)
        self.assertEqual(len(set(r['review_id'] for r in records)),7)

    def test_non_overwrite(self):
        with self.assertRaisesRegex(ValueError,'ya existe'):
            audit(self.resultdir)


if __name__=='__main__':
    unittest.main()
