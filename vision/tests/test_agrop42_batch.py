"""AGROP-42 / Incremento 03: pruebas de lote, integridad, trazabilidad y tiempos."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vision.evaluation.agrop42.procesar_lotes import (
    BatchInputError, _load_inventory, _locate_image, _process_image, process_dataset,
)


class BatchProcessingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.dataset = self.root / 'dataset'
        (self.dataset / 'images').mkdir(parents=True)
        self.rows = []

    def photo(self, product='mango', rgb=(140, 165, 40), rid=None,
              rights=True, eligible=True, piece=False, session=False):
        rid = rid or f'REG-{len(self.rows) + 1:05d}'
        img = Image.new('RGB', (200, 150), (150, 150, 151))
        ImageDraw.Draw(img).ellipse((35, 12, 164, 140), fill=rgb)
        temp = self.root / f'{rid}.png'
        img.save(temp)
        sha = hashlib.sha256(temp.read_bytes()).hexdigest()
        (self.dataset / 'images' / f'{sha}.png').write_bytes(temp.read_bytes())
        item = {
            'record_id': rid, 'product': product, 'sha256': sha,
            'image_path': f'images/{sha}.png',
            'visible_to_audit': eligible, 'rights_confirmed_declared': rights,
            'piece_identity_declared': piece, 'piece_id': 'P-1' if piece else None,
            'device_id': 'ESP-1' if session else None,
            'boot_id': 'BOOT-1' if session else None,
            'variety_declared': 'Kent' if product == 'mango' else None,
            'variety_confirmed_declared': False,
            'source_id': 'test', 'source_url': 'https://example.invalid/photo',
            'license': 'CC0',
        }
        self.rows.append(item)
        return item

    def inventory(self):
        (self.dataset / 'inventory.json').write_text(json.dumps(self.rows), encoding='utf-8')

    def process(self, repeats=1, previews=False):
        self.inventory()
        return process_dataset(self.dataset, self.root / 'output', repeats=repeats, previews=previews)

    def test_dos_productos_con_analisis_y_sin_clasificacion(self):
        self.photo('mango', (150, 180, 50))
        self.photo('tomate', (220, 35, 24))
        summary = self.process()
        self.assertEqual(summary['processed_unique_sha256'], 2)
        self.assertEqual(summary['products']['mango']['processed_unique_images'], 1)
        self.assertEqual(summary['products']['tomate']['processed_unique_images'], 1)
        self.assertTrue(all(x['decision_tecnica'] == 'revision_trazabilidad_pendiente' for x in summary['images']))
        for item in summary['images']:
            result = json.loads((self.root / 'output' / item['result_file']).read_text())
            self.assertTrue(result['sha256_verified'])
            self.assertIsNone(result['predicted_visual_label'])
            self.assertFalse(result['defect_detection_performed'])
            self.assertFalse(result['commercial_quality_assessed'])
            self.assertEqual(result['rubric_status'], 'no_evaluable_sin_control_de_captura')

    def test_mascara_tomate_es_el_adaptador_propio(self):
        self.photo('tomate', (205, 45, 30))
        summary = self.process()
        path = self.root / 'output' / summary['images'][0]['result_file']
        data = json.loads(path.read_text())
        self.assertEqual(data['surface_analysis']['product'], 'tomate')
        self.assertNotIn('verified_as_mango', str(data['surface_analysis']['candidates']))
        self.assertEqual(data['mask_analysis']['product'], 'tomate')

    def test_imagen_y_fuente_conservan_sha256(self):
        item = self.photo()
        self.process(previews=True)
        content = (self.dataset / item['image_path']).read_bytes()
        self.assertEqual(hashlib.sha256(content).hexdigest(), item['sha256'])
        self.assertTrue((self.root / 'output' / 'previews').is_dir())
        self.assertEqual(len(list((self.root / 'output' / 'previews').glob('*.png'))), 2)

    def test_repeticiones_producen_descriptores_estables(self):
        self.photo()
        summary = self.process(repeats=3)
        self.assertEqual(summary['products']['mango']['timing']['runs'], 3)
        self.assertEqual(summary['products']['mango']['timing']['scope'],
                         'lectura_sha256_decodificacion_segmentacion_provisional_mascaras')

    def test_no_confundir_tiempo_con_inferencia_esp32(self):
        self.photo()
        summary = self.process()
        self.assertEqual(summary['environment']['hardware_scope'], 'equipo_ejecutor_de_Python_no_dispositivo_ESP32')
        self.assertEqual(summary['environment']['memory_peak'], 'no_medido')
        self.assertIsNone(summary['comparison']['accuracy'])
        self.assertFalse(summary['comparison']['same_test_set_comparison_performed'])

    def test_dos_filas_con_mismo_sha_son_un_solo_archivo(self):
        first = self.photo()
        other = dict(first, record_id='REG-00002')
        self.rows.append(other)
        summary = self.process()
        self.assertEqual(summary['input_inventory_records'], 2)
        self.assertEqual(summary['processed_unique_sha256'], 1)
        self.assertEqual(summary['processed_linked_records'], 2)
        self.assertEqual(summary['images'][0]['linked_record_ids'], ['REG-00001', 'REG-00002'])

    def test_mismo_sha_entre_productos_se_excluye(self):
        first = self.photo()
        self.rows.append(dict(first, record_id='REG-00002', product='tomate'))
        summary = self.process()
        self.assertEqual(summary['processed_unique_sha256'], 0)
        self.assertEqual(len(summary['excluded_records']), 2)
        self.assertEqual(summary['excluded_records'][0]['reason'], 'mismo_sha256_en_productos_distintos')

    def test_licencia_o_fuente_no_aceptada_no_se_procesa(self):
        self.photo(rights=False)
        self.photo(product='tomate', rgb=(210, 40, 30), eligible=False)
        summary = self.process()
        self.assertEqual(summary['processed_unique_sha256'], 0)
        self.assertEqual(len(summary['excluded_records']), 2)

    def test_no_afirma_que_pieza_y_sesion_sean_ground_truth(self):
        self.photo(piece=True, session=True)
        summary = self.process()
        path = self.root / 'output' / summary['images'][0]['result_file']
        result = json.loads(path.read_text())
        self.assertTrue(result['piece_identity_confirmed_declared'])
        self.assertTrue(result['session_documented'])
        self.assertFalse(result['capture_quality_verified'])
        self.assertEqual(result['decision_tecnica'], 'revision_de_captura_pendiente')
        self.assertIsNone(result['predicted_visual_label'])

    def test_rechaza_sha_modificado_en_archivo(self):
        row = self.photo()
        path = self.dataset / row['image_path']
        path.write_bytes(path.read_bytes() + b'alterado')
        summary = self.process()
        self.assertEqual(summary['processed_unique_sha256'], 0)
        self.assertIn('SHA256', summary['excluded_records'][0]['reason'])

    def test_rechaza_entrada_sin_foto(self):
        row = self.photo()
        (self.dataset / row['image_path']).unlink()
        summary = self.process()
        self.assertEqual(summary['processed_unique_sha256'], 0)
        self.assertIn('no disponible', summary['excluded_records'][0]['reason'])

    def test_rechaza_ruta_escapando_del_dataset(self):
        self.photo()
        self.rows[0]['image_path'] = '../outside.png'
        with self.assertRaises(BatchInputError):
            self.process()

    def test_rechaza_duplicado_de_id_en_inventario(self):
        a = self.photo()
        self.rows.append(dict(a))
        self.inventory()
        with self.assertRaises(BatchInputError):
            _load_inventory(self.dataset)

    def test_no_sobrescribe_salida_existente(self):
        self.photo()
        self.process()
        with self.assertRaises(BatchInputError):
            process_dataset(self.dataset, self.root / 'output')

    def test_no_acepta_salida_dentro_del_dataset(self):
        self.photo()
        self.inventory()
        with self.assertRaises(BatchInputError):
            process_dataset(self.dataset, self.dataset / 'resultados')

    def test_repeticiones_fuera_de_rango(self):
        self.photo()
        self.inventory()
        for count in (0, 11, True):
            with self.subTest(count=count), self.assertRaises(BatchInputError):
                process_dataset(self.dataset, self.root / 'output', repeats=count)

    def test_no_usa_mango_desconocido_como_kent(self):
        item = self.photo()
        item['variety_declared'] = None
        item['variety_confirmed_declared'] = False
        summary = self.process()
        data = json.loads((self.root / 'output' / summary['images'][0]['result_file']).read_text())
        self.assertIsNone(data['source_provenance'][0]['variety_declared'])
        self.assertFalse(data['source_provenance'][0]['variety_confirmed_declared'])

    def test_resultados_deterministas_sin_contar_tiempos(self):
        self.photo()
        self.inventory()
        first = process_dataset(self.dataset, self.root / 'run1', repeats=1, previews=False)
        second = process_dataset(self.dataset, self.root / 'run2', repeats=1, previews=False)
        for x, y in zip(first['images'], second['images']):
            dx = json.loads((self.root / 'run1' / x['result_file']).read_text())
            dy = json.loads((self.root / 'run2' / y['result_file']).read_text())
            dx.pop('processing_timing')
            dy.pop('processing_timing')
            self.assertEqual(dx, dy)


if __name__ == '__main__':
    unittest.main()
