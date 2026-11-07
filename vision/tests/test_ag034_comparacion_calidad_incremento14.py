"""Contratos AG-034 de software. Las imágenes/etiquetas aquí son sintéticas de prueba."""
from __future__ import annotations

import contextlib
import csv
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from vision.evaluation.agrop42.comparar_calidad_ag034 import (
    COLUMNS, QualityError, aggregate_pieces, benchmark, connected_groups,
    fit_light, fit_rule, main, metrics, read_csv, safe_path, split_groups,
)


class CalidadAG034Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.images = self.base / 'imagenes'
        self.supports = self.base / 'soportes'
        self.images.mkdir()
        self.supports.mkdir()
        (self.supports / 'revisiones.txt').write_text('Prueba del contrato, NO revisión real', encoding='utf-8')
        (self.supports / 'sesiones.txt').write_text('Prueba del contrato, NO captura real', encoding='utf-8')
        self.csv = self.base / 'etiquetas.csv'
        self.rows = []
        self.save()

    def save(self):
        with self.csv.open('w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(self.rows)

    def add(self, product, grade, idx, *, session=None, variety=None, same_image=False):
        name = f'{product}_{grade}_{idx}.png'
        file = self.images / name
        base = {'E0': (45, 170, 55), 'E1': (170, 100, 38), 'E2': (145, 40, 35)}[grade]
        if same_image:
            file.write_bytes((self.images / f'{product}_{grade}_0.png').read_bytes())
        else:
            image = Image.new('RGB', (32, 24), base)
            image.putpixel((0, 0), (idx + 1, 7 if product == 'mango' else 8, 2))
            image.save(file)
        self.rows.append({
            'producto': product,
            'variedad_declarada': variety if variety is not None else ('Kent' if product == 'mango' else '-'),
            'pieza_id': f'{product}_{grade}_{idx}',
            'sesion_id': session or f'sesion_{product}_{grade}_{idx}',
            'imagen_relativa': name,
            'sha256_imagen': hashlib.sha256(file.read_bytes()).hexdigest(),
            'roi_xywh': '[2,2,25,18]', 'roi_verificada': 'si',
            'estado_revision': 'etiquetada', 'etiqueta_e0_e1_e2': grade,
            'revisor_id': 'operador_01', 'fecha_revision_iso': '2026-11-06T10:00:00-05:00',
            'rubrica_version': 'kent-ext-v0.5' if product == 'mango' else 'tomato-ext-v0.1',
            'soporte_revision_relativo': 'revisiones.txt',
            'soporte_identidad_sesion_relativo': 'sesiones.txt',
        })
        self.save()

    def sample(self, p='mango', count=5):
        for grade in ('E0', 'E1', 'E2'):
            for i in range(count):
                self.add(p, grade, i)

    def test_plantilla_vacia_bloquea_ambos_productos_sin_metricas(self):
        report = benchmark(self.csv, self.images, self.supports)
        self.assertEqual(report['piezas_elegibles'], 0)
        for p in ('mango', 'tomate'):
            self.assertEqual(report['por_producto'][p]['estado'], 'bloqueado_por_datos_insuficientes')
            self.assertIsNone(report['por_producto'][p]['metricas'])
        self.assertFalse(report['cierre_total_AG034_acreditado'])

    def test_soporte_declarado_no_equivale_a_certificacion(self):
        self.sample('mango')
        report = benchmark(self.csv, self.images, self.supports)
        item = report['por_producto']['mango']
        self.assertEqual(item['estado'], 'comparacion_experimental_provisional')
        self.assertEqual(item['reparto_por_pieza'], {'entrenamiento': 9, 'validacion': 3, 'prueba': 3})
        self.assertEqual(set(item['prueba_comun']), {'reglas', 'modelo_ligero'})
        self.assertTrue(set(item['ids_por_particion']['entrenamiento']).isdisjoint(item['ids_por_particion']['prueba']))
        self.assertFalse(report['validacion_humana_independiente_acreditada_por_software'])
        self.assertFalse(report['integracion_productiva_autorizada'])
        self.assertFalse(report['cierre_total_AG034_acreditado'])

    def test_salida_determinista_por_datos_y_semilla(self):
        self.sample('tomate')
        first = benchmark(self.csv, self.images, self.supports)
        second = benchmark(self.csv, self.images, self.supports)
        self.assertEqual(first, second)

    def test_una_sesion_para_todas_las_piezas_bloquea_splits(self):
        for grade in ('E0', 'E1', 'E2'):
            for idx in range(5):
                self.add('mango', grade, idx, session='una_sesion')
        report = benchmark(self.csv, self.images, self.supports)
        self.assertEqual(report['por_producto']['mango']['componentes_pieza_sesion'], 1)
        self.assertEqual(report['por_producto']['mango']['estado'], 'bloqueado_por_datos_insuficientes')

    def test_clase_ausente_bloquea_modelo_calidad(self):
        for idx in range(7):
            self.add('tomate', 'E0', idx)
            self.add('tomate', 'E1', idx)
        report = benchmark(self.csv, self.images, self.supports)
        self.assertEqual(report['por_producto']['tomate']['estado'], 'bloqueado_por_datos_insuficientes')

    def test_variedad_ataulfo_no_se_usa_como_kent(self):
        self.add('mango', 'E0', 0, variety='Ataulfo')
        with self.assertRaisesRegex(QualityError, 'Kent'):
            benchmark(self.csv, self.images, self.supports)

    def test_sha_falso_rechazado(self):
        self.add('tomate', 'E0', 0)
        self.rows[0]['sha256_imagen'] = '0'*64
        self.save()
        with self.assertRaisesRegex(QualityError, 'SHA256'):
            benchmark(self.csv, self.images, self.supports)

    def test_identidad_de_imagen_duplicada_rechazada(self):
        self.add('tomate', 'E0', 0)
        self.add('tomate', 'E0', 1, same_image=True)
        with self.assertRaisesRegex(QualityError, 'otra pieza'):
            benchmark(self.csv, self.images, self.supports)

    def test_roi_falsa_rechazada(self):
        self.add('mango', 'E0', 0)
        self.rows[0]['roi_xywh'] = '[0,0,9999,9999]'
        self.save()
        with self.assertRaisesRegex(QualityError, 'ROI fuera'):
            benchmark(self.csv, self.images, self.supports)

    def test_revisor_artificial_rechazado(self):
        self.add('mango', 'E0', 0)
        self.rows[0]['revisor_id'] = 'ChatGPT'
        self.save()
        with self.assertRaisesRegex(QualityError, 'humano'):
            benchmark(self.csv, self.images, self.supports)

    def test_soporte_inexistente_rechazado(self):
        self.add('tomate', 'E0', 0)
        self.rows[0]['soporte_revision_relativo'] = 'no_hay.txt'
        self.save()
        with self.assertRaisesRegex(QualityError, 'No existe evidencia'):
            benchmark(self.csv, self.images, self.supports)

    def test_traversal_rechazado(self):
        self.add('tomate', 'E0', 0)
        self.rows[0]['imagen_relativa'] = '../secreto.png'
        self.save()
        with self.assertRaisesRegex(QualityError, 'Ruta relativa insegura'):
            benchmark(self.csv, self.images, self.supports)

    def test_estado_pendiente_no_se_entrena(self):
        self.add('tomate', 'E0', 0)
        self.rows[0]['estado_revision'] = 'pendiente'
        self.rows[0]['etiqueta_e0_e1_e2'] = ''
        self.save()
        report = benchmark(self.csv, self.images, self.supports)
        self.assertEqual(report['piezas_elegibles'], 0)
        self.assertIsNone(report['por_producto']['tomate']['metricas'])

    def test_revisor_sin_timezone_rechazado(self):
        self.add('mango', 'E0', 0)
        self.rows[0]['fecha_revision_iso'] = '2026-11-06T10:00:00'
        self.save()
        with self.assertRaisesRegex(QualityError, 'horaria'):
            benchmark(self.csv, self.images, self.supports)

    def test_labels_contradictorias_pieza_rechazadas(self):
        self.add('tomate', 'E0', 0)
        row = dict(self.rows[0])
        row['imagen_relativa'] = 'otra_vista.png'
        second = self.images / 'otra_vista.png'
        Image.new('RGB', (32,24), (90,30,15)).save(second)
        row['sha256_imagen'] = hashlib.sha256(second.read_bytes()).hexdigest()
        row['etiqueta_e0_e1_e2'] = 'E1'
        self.rows.append(row)
        self.save()
        with self.assertRaisesRegex(QualityError, 'contradictorias'):
            benchmark(self.csv, self.images, self.supports)

    def test_archivos_resultados_no_se_sobrescriben(self):
        out = self.base / 'out.json'
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['--csv', str(self.csv), '--raiz-imagenes', str(self.images),
                                   '--raiz-soportes', str(self.supports), '--salida', str(out)]), 0)
            self.assertEqual(main(['--csv', str(self.csv), '--raiz-imagenes', str(self.images),
                                   '--raiz-soportes', str(self.supports), '--salida', str(out)]), 2)
        self.assertEqual(json.loads(out.read_text(encoding='utf-8'))['piezas_elegibles'], 0)


if __name__ == '__main__':
    unittest.main()
