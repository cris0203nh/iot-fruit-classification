"""Contratos y seguridad del Incremento 10, con fotografías artificiales SOLO de test."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from PIL import Image

from vision.evaluation.agrop42.perfil_recursos_ag034 import (
    _cargar_muestras, _percentil, _validar_archivo, ejecutar, main,
)


def build_zip(path: Path, *, wrong_hash=False, repeated_sha=False,
              invalid_path=False, same_source_group=False,
              duplicate_id_path=False, omitted_image=False,
              fewer_groups=False) -> None:
    entries = []
    images = []
    for product in ('mangos', 'tomates'):
        for number in range(1, (4 if fewer_groups else 5) + 1):
            piece_id = ('MANGO' if product == 'mangos' else 'TOMATE') + f'_{number:02d}'
            name = f'{product}/{piece_id}/vista_01.jpg'
            if invalid_path and number == 1 and product == 'mangos':
                name = f'{product}/../{piece_id}/vista_01.jpg'
            image = Image.new('RGB', (48, 48), (250, 246, 245))
            rgb = (248, 175, 28) if product == 'mangos' else (230, 37, 48)
            for x in range(10, 35):
                for y in range(7, 40):
                    image.putpixel((x, y), rgb)
            mem = io.BytesIO()
            image.save(mem, format='JPEG', quality=87 + number)
            payload = mem.getvalue()
            if repeated_sha and number == 2 and product == 'mangos':
                payload = images[0][1]
            sha = hashlib.sha256(payload).hexdigest()
            if wrong_hash and number == 1 and product == 'mangos':
                sha = '0' * 64
            images.append((name, payload))
            entries.append({
                'archivo': name,
                'id_ejemplar': ('MANGO_99' if duplicate_id_path and number == 1 and product == 'mangos' else piece_id),
                'sha256': sha,
                'grupo_original': ('misma_fuente' if same_source_group and product == 'mangos' else f'{product}_{number}'),
                'fuente': f'fuente_{product}',
            })
    with ZipFile(path, 'w') as z:
        for name, payload in images:
            if omitted_image and name == images[0][0]:
                continue
            z.writestr(name, payload)
        mem = io.StringIO()
        writer = csv.DictWriter(mem, fieldnames=list(entries[0]))
        writer.writeheader()
        writer.writerows(entries)
        z.writestr('trazabilidad.csv', mem.getvalue())


class PerfilRecursosAG034Tests(unittest.TestCase):
    def test_informe_perfil_comparable_y_no_autoriza_entrenamiento(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zipfile = root / 'dataset.zip'
            build_zip(zipfile)
            result = ejecutar(zipfile, root / 'resultado', repeticiones=2,
                              bucles=10, repeticiones_pipeline=1)
            self.assertEqual(result['dataset']['vistas'], 10)
            self.assertEqual(result['dataset']['particion_vistas']['prueba'], 2)
            self.assertEqual(result['dataset']['particion_ids_fuente'],
                             {'entrenamiento':6,'validacion':2,'prueba':2})
            self.assertEqual(set(result['enfoques']), {'reglas', 'modelo_ligero'})
            for method in result['enfoques'].values():
                self.assertEqual(method['n_vistas_test'], 2)
                self.assertGreaterEqual(method['inferencia_sin_extraccion']['mediana_ms'], 0)
                self.assertGreater(method['pipeline_completo_en_equipo_local']['mediana_ms'], 0)
                self.assertGreater(method['modelo_json_bytes'], 0)
            self.assertFalse(result['decision']['cierre_total_AG034_acreditado'])
            self.assertFalse(result['decision']['hardware_objetivo_validado'])
            self.assertFalse(result['decision']['clasificacion_e0_e1_e2_evaluada'])
            self.assertEqual(sorted(p.name for p in (root / 'resultado').iterdir()), [
                'AG034_cuadro_comparativo.csv', 'AG034_informe_rendimiento.md',
                'AG034_perfil_recursos.json'])
            manifest = json.loads((root/'resultado'/'AG034_perfil_recursos.json').read_text('utf-8'))
            self.assertEqual(manifest['zip_sha256'], hashlib.sha256(zipfile.read_bytes()).hexdigest())
            self.assertNotIn('predicciones_de_defectos', manifest)
            self.assertIn('E0/E1/E2', (root/'resultado'/'AG034_informe_rendimiento.md').read_text('utf-8'))

    def test_no_sobrescribe_resultados(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); output = root/'salida'; output.mkdir()
            p = root/'dataset.zip'; build_zip(p)
            with self.assertRaises(FileExistsError): ejecutar(p, output, repeticiones=2, bucles=10)

    def test_sha_incorrecto_rechazado(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'dataset.zip'; build_zip(p, wrong_hash=True)
            with self.assertRaisesRegex(ValueError, 'SHA-256'):_cargar_muestras(p)

    def test_sha_duplicado_rechazado(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'dataset.zip'; build_zip(p, repeated_sha=True)
            with self.assertRaisesRegex(ValueError, 'duplicada por SHA-256'):_cargar_muestras(p)

    def test_ruta_traversal_rechazada(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'dataset.zip'; build_zip(p, invalid_path=True)
            with self.assertRaisesRegex(ValueError, 'Ruta de imagen'):_cargar_muestras(p)

    def test_identificador_no_coincidente_rechazado(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'dataset.zip'; build_zip(p, duplicate_id_path=True)
            with self.assertRaisesRegex(ValueError, 'inconsistente'):_cargar_muestras(p)

    def test_grupo_fuente_reutilizado_entre_ids_rechazado(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'dataset.zip'; build_zip(p, same_source_group=True)
            with self.assertRaisesRegex(ValueError, 'Grupo original compartido'):_cargar_muestras(p)

    def test_imagen_faltante_rechazada(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'dataset.zip'; build_zip(p, omitted_image=True)
            with self.assertRaisesRegex(ValueError, 'ausente'):_cargar_muestras(p)

    def test_insuficiencia_grupos_no_inventa_comparacion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); p = root/'dataset.zip'; build_zip(p, fewer_groups=True)
            with self.assertRaisesRegex(ValueError, 'grupos por producto'):
                ejecutar(p, root/'salida', repeticiones=2, bucles=10)
            self.assertFalse((root/'salida').exists())

    def test_rutas_absolutas_y_windows_rechazadas(self):
        for name in ('../../etc/passwd', '/mangos/MANGO_01/vista.jpg',
                     'mangos\\MANGO_01\\vista.jpg', 'C:/mangos/MANGO_01/vista.jpg',
                     'tomates/TOMATE_01/../../otra.jpg'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                _validar_archivo(name)

    def test_percentil_lineal_y_valores_vacios(self):
        self.assertEqual(_percentil([1, 3, 5], .95), 4.8)
        with self.assertRaises(ValueError): _percentil([], .95)

    def test_parametros_fuera_de_rango(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                ejecutar(Path(tmp)/'no.zip', Path(tmp)/'out', repeticiones=1)

    def test_cli_falla_sin_zip_sin_crear_salida(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)/'salida'
            self.assertEqual(main(['--zip',str(Path(tmp)/'no.zip'),'--salida',str(target)]),2)
            self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
