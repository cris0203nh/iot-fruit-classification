"""AG-055 I02: pruebas con evidencia SINTÉTICA únicamente del contrato de software."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from pathlib import Path

from PIL import Image

from vision.ag055.dataset_i02 import (
    DatasetError, FIELDS, consolidar, inventariar, read_rows, write_rows,
)
from vision.ag055 import dataset_i02 as dataset_module
from vision.ag055.dataset_i02 import _private_output as _production_private_output
from vision.evaluation.ag036.auditar_etiquetado import UNIVERSE_COLS, REVIEW_COLS
from vision.evaluation.agrop42.comparar_calidad_ag034 import COLUMNS, load_eligible


class DatasetI02Tests(unittest.TestCase):
    def setUp(self):
        # Solo evidencias sinteticas creadas por el propio test, nunca datos privados.
        repo = Path(__file__).resolve().parents[2]
        self.temp = tempfile.TemporaryDirectory(prefix='.ag055-test-', dir=repo)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

        # El codigo de produccion sigue prohibiendo salidas privadas bajo Git.
        # Esta excepcion existe SOLO dentro del fixture sintetico de unittest.
        original = dataset_module._private_output
        def synthetic_output(path):
            target = path.resolve()
            if not target.is_relative_to(self.root):
                return original(path)
            if path.exists():
                raise DatasetError('Directorio de salida existente: no se sobrescribe')
            if not path.parent.is_dir():
                raise DatasetError('Primero crea la carpeta padre')

        guard = patch.object(dataset_module, '_private_output', synthetic_output)
        guard.start()
        self.addCleanup(guard.stop)
        self.images = self.root / 'imagenes'; self.images.mkdir()
        self.universe = self.root / 'universo.csv'
        self.zip = self.root / 'devolucion_A.zip'
        self.prep = self.root / 'preparacion'
        self.output = self.root / 'consolidado'
        self.photos = []
        self.reviews = []
        for product, grade, lot, piece, variety, rubric in (
            ('mango', 'E1', 'L-M', 'PM', 'Kent', 'kent-ext-v0.4'),
            ('tomate', 'E0', 'L-T', 'PT', 'rojo', 'tomato-ext-v0.2'),
        ):
            name = f'{product}.png'
            img = Image.new('RGB', (80, 72), (220, 140, 25) if product == 'mango' else (220, 15, 30))
            img.putpixel((3, 3), (1, 2, 3)); img.save(self.images / name)
            self.photos.append({
                'producto': product, 'variedad_declarada': variety, 'lote_id': lot,
                'pieza_id': piece, 'sesion_id': 'S-' + piece,
                'imagen_relativa': name,
                'sha256_imagen': hashlib.sha256((self.images / name).read_bytes()).hexdigest(),
                'rubrica_version': rubric, 'seleccion_doble': 'si', 'criterio_seleccion': 'piloto',
            })
            self.reviews.append({
                'producto': product, 'lote_id': lot, 'pieza_id': piece,
                'revisor_id': 'REV_A1', 'fecha_revision_iso': '2026-11-09T12:00:00-05:00',
                'rubrica_version': rubric, 'estado_revision': 'etiquetada',
                'etiqueta_e0_e1_e2': grade, 'justificacion': 'Revisión humana de prueba contractual',
                'criterios_rxx': 'R03' if grade == 'E1' else '',
                'ubicacion_evidencia': 'vista frente, cuadrante' if grade == 'E1' else '',
                'soporte_relativo': product + '.txt',
            })
        self.save()

    def save(self):
        with self.universe.open('w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=UNIVERSE_COLS); w.writeheader(); w.writerows(self.photos)
        stream = io.StringIO(newline='')
        w = csv.DictWriter(stream, fieldnames=REVIEW_COLS); w.writeheader(); w.writerows(self.reviews)
        with zipfile.ZipFile(self.zip, 'w') as z:
            z.writestr('revision_A.csv', stream.getvalue().encode('utf-8-sig'))
            for r in self.reviews:
                z.writestr('soportes/' + r['soporte_relativo'], 'Soporte humano declarado (solo test)')

    def run_inventory(self):
        return inventariar(self.universe, self.images, self.zip, self.prep)

    def mark_reviewed(self):
        rows = read_rows(self.prep / 'AG055_I02_fichas_verificacion.csv', FIELDS)
        proofs = self.prep / 'soportes' / 'acreditaciones'
        proofs.mkdir()
        for name in ('licencia.txt', 'identidad.txt', 'rubrica.txt', 'variedad.txt'):
            (proofs / name).write_text('Archivo solo de prueba, no acredita nada fuera del test', encoding='utf-8')
        for row in rows:
            row.update({
                'roi_xywh': '[3,4,50,40]', 'roi_verificada': 'si',
                'derechos_uso': 'permitido', 'soporte_derechos_relativo': 'acreditaciones/licencia.txt',
                'identidad_sesion_verificada': 'si',
                'soporte_identidad_sesion_relativo': 'acreditaciones/identidad.txt',
                'rubrica_aprobada': 'si', 'soporte_rubrica_relativo': 'acreditaciones/rubrica.txt',
                'variedad_verificada': 'si', 'soporte_variedad_relativo': 'acreditaciones/variedad.txt',
            })
        (self.prep / 'AG055_I02_fichas_verificacion.csv').unlink()
        write_rows(self.prep / 'AG055_I02_fichas_verificacion.csv', FIELDS, rows)
        return rows

    def test_guardia_original_rechaza_salida_privada_en_git(self):
        # Verifica expresamente la proteccion real, fuera del mock sintetico.
        with self.assertRaisesRegex(DatasetError, 'repositorio'):
            _production_private_output(self.root / 'no_debe_existir')

    def test_inventario_conserva_etiquetas_y_no_aprueba_dataset(self):
        report = self.run_inventory()
        self.assertEqual(report['piezas_con_etiqueta_A'], 2)
        self.assertFalse(report['doble_concordancia_verificada'])
        rows = read_rows(self.prep / 'AG055_I02_fichas_verificacion.csv', FIELDS)
        self.assertEqual({r['etiqueta_reportada_A'] for r in rows}, {'E0', 'E1'})
        self.assertTrue(all(r['roi_verificada'] == 'no' for r in rows))
        out = consolidar(self.prep, self.output)
        self.assertEqual(out['vistas_elegibles_AG034'], 0)
        self.assertFalse(out['despliegue_automatico_autorizado'])
        self.assertEqual(out['productos']['tomate']['faltantes_minimos_por_grado']['E1'], 5)
        self.assertEqual(len(read_rows(self.output/'AG055_I02_etiquetas_elegibles_AG034.csv', COLUMNS)), 0)

    def test_promocion_con_evidencias_generadas_exclusivamente_en_test(self):
        self.run_inventory(); self.mark_reviewed()
        out = consolidar(self.prep, self.output)
        self.assertEqual(out['vistas_elegibles_AG034'], 2)
        self.assertEqual(out['piezas_elegibles_AG034'], 2)
        self.assertEqual(out['productos']['mango']['grupos_independientes_por_grado']['E1'], 1)
        self.assertEqual(out['productos']['tomate']['grupos_independientes_por_grado']['E0'], 1)
        rows, info = load_eligible(self.output/'AG055_I02_etiquetas_elegibles_AG034.csv',
                                   self.images, self.prep/'soportes')
        self.assertEqual(len(rows), 2)
        self.assertEqual(info['vistas_elegibles'], 2)
        self.assertFalse(out['modelo_entrenado'])

    def test_no_permite_mutar_etiquetas_humanas(self):
        self.run_inventory()
        rows = read_rows(self.prep / 'AG055_I02_fichas_verificacion.csv', FIELDS)
        rows[0]['etiqueta_reportada_A'] = 'E2'
        (self.prep/'AG055_I02_fichas_verificacion.csv').unlink()
        write_rows(self.prep/'AG055_I02_fichas_verificacion.csv', FIELDS, rows)
        with self.assertRaisesRegex(DatasetError, 'alterado'):
            consolidar(self.prep, self.output)

    def test_no_sobrescribe_un_inventario_previo(self):
        self.run_inventory()
        with self.assertRaisesRegex(DatasetError, 'existente'):
            self.run_inventory()

    def test_fuente_original_alterada_bloquea_consolidacion(self):
        self.run_inventory()
        self.zip.write_bytes(b'ZIP alterado')
        with self.assertRaisesRegex(DatasetError, 'fuente cambió'):
            consolidar(self.prep, self.output)

    def test_roi_sin_soportes_no_se_promueve(self):
        self.run_inventory()
        rows = read_rows(self.prep/'AG055_I02_fichas_verificacion.csv', FIELDS)
        rows[0]['roi_verificada'] = 'si'; rows[0]['roi_xywh'] = '[1,1,20,20]'
        (self.prep/'AG055_I02_fichas_verificacion.csv').unlink()
        write_rows(self.prep/'AG055_I02_fichas_verificacion.csv', FIELDS, rows)
        report = consolidar(self.prep, self.output)
        self.assertEqual(report['vistas_elegibles_AG034'], 0)

    def test_dos_fotografias_de_una_pieza_no_inflan_su_conteo(self):
        original = self.photos[0].copy()
        different = self.images / 'mango_vista_2.png'
        image = Image.new('RGB', (80, 72), (120, 180, 80))
        image.save(different)
        original['imagen_relativa'] = different.name
        original['sha256_imagen'] = hashlib.sha256(different.read_bytes()).hexdigest()
        self.photos.append(original)
        self.save()
        report = self.run_inventory()
        self.assertEqual(report['vistas_inventario'], 3)
        self.assertEqual(report['piezas_con_etiqueta_A'], 2)
        self.mark_reviewed()
        out = consolidar(self.prep, self.output)
        self.assertEqual(out['vistas_elegibles_AG034'], 3)
        self.assertEqual(out['piezas_elegibles_AG034'], 2)

    def test_licencia_pendiente_impide_promocion_selectiva(self):
        self.run_inventory()
        rows = self.mark_reviewed()
        for r in rows:
            if r['producto'] == 'tomate':
                r['derechos_uso'] = 'pendiente'
        (self.prep / 'AG055_I02_fichas_verificacion.csv').unlink()
        write_rows(self.prep / 'AG055_I02_fichas_verificacion.csv', FIELDS, rows)
        out = consolidar(self.prep, self.output)
        self.assertEqual(out['vistas_elegibles_AG034'], 1)
        self.assertEqual(out['piezas_elegibles_AG034'], 1)
        self.assertEqual(out['motivos_exclusion_por_vista'].get('licencia_o_uso_pendiente'), 1)

    def test_etiquetas_no_se_infieren_de_pruebas(self):
        self.run_inventory()
        fichas = read_rows(self.prep / 'AG055_I02_fichas_verificacion.csv', FIELDS)
        self.assertEqual(len(fichas), 2)
        self.assertEqual({r['revisor_id_A'] for r in fichas}, {'REV_A1'})
        self.assertTrue(all(r['soporte_revision_A_relativo'].startswith('AG036_A/') for r in fichas))


if __name__ == '__main__':
    unittest.main()
