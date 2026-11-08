"""Pruebas sintéticas del EMPAQUETADOR: nunca son etiquetas reales de fruta."""
import csv
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

from vision.evaluation.ag036.auditar_etiquetado import AuditError, UNIVERSE_COLS
from vision.evaluation.ag036.preparar_paquetes_revision import prepare, main


class PaquetesRevisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.images = self.root / 'imagenes'
        self.images.mkdir()
        self.csv = self.root / 'universo.csv'
        self.output = self.root / 'entrega'
        self.rows = []
        self.save()

    def save(self):
        with self.csv.open('w', encoding='utf-8', newline='') as out:
            writer = csv.DictWriter(out, fieldnames=UNIVERSE_COLS)
            writer.writeheader()
            writer.writerows(self.rows)

    def put(self, piece, *, product='tomate', variety='Roma', suffix=1,
            selected='si', lot='LOTE1', rubric=None, rel=None):
        rel = rel or f'{lot}_{piece}_{suffix}.png'
        path = self.images / rel
        path.parent.mkdir(exist_ok=True, parents=True)
        # Pruebas: fotografías sintéticas distintas por pieza, nunca dataset real.
        seed = sum(map(ord, rel))
        Image.new('RGB', (96, 64), (seed % 240, seed % 171, seed % 149)).save(path)
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        self.rows.append(dict(zip(UNIVERSE_COLS, [
            product, variety, lot, piece, f'S-{piece}', rel, sha,
            rubric or ('kent-ext-v0.4' if product == 'mango' else 'tomato-ext-v0.2'),
            selected, 'selección documentada antes de revisión' if selected == 'si' else '',
        ])))
        self.save()
        return self.rows[-1]

    def test_prepara_dos_paquetes_ciegos_y_acta(self):
        self.put('P001', product='mango', variety='Kent')
        self.put('P002')
        result = prepare(self.csv, self.images, self.output)
        self.assertEqual(result['piezas'], 2)
        self.assertEqual(result['vistas'], 2)
        self.assertFalse(result['cierre_total_AG036_acreditado'])
        a = self.output / 'AG036_Revisor_A.zip'
        b = self.output / 'AG036_Revisor_B.zip'
        self.assertTrue(a.is_file() and b.is_file())
        for slot, archive in [('A', a), ('B', b)]:
            with zipfile.ZipFile(archive) as z:
                self.assertIsNone(z.testzip())
                self.assertIn('indice.html', z.namelist())
                self.assertIn('inventario_vistas.json', z.namelist())
                self.assertIn(f'revision_{slot}.csv', z.namelist())
                self.assertNotIn(f'revision_{"B" if slot == "A" else "A"}.csv', z.namelist())
                rd = csv.DictReader(io.StringIO(z.read(f'revision_{slot}.csv').decode('utf-8-sig')))
                reviews = list(rd)
                self.assertEqual(len(reviews), 2)
                self.assertTrue(all(not x['revisor_id'] and not x['etiqueta_e0_e1_e2'] for x in reviews))
                self.assertEqual(sum(n.startswith('imagenes/') for n in z.namelist()), 2)
        act = json.loads((self.output / 'AG036_acta_preparacion.json').read_text(encoding='utf-8'))
        self.assertEqual(act['etiquetas_generadas_automaticamente'], 0)
        self.assertEqual(act['sha256_zips']['A'], hashlib.sha256(a.read_bytes()).hexdigest())
        self.assertEqual(act['sha256_zips']['B'], hashlib.sha256(b.read_bytes()).hexdigest())

    def test_multiples_vistas_solo_una_fila(self):
        self.put('P001', suffix=1)
        self.put('P001', suffix=2)
        self.assertEqual(prepare(self.csv, self.images, self.output)['vistas'], 2)
        with zipfile.ZipFile(self.output / 'AG036_Revisor_A.zip') as z:
            rows = list(csv.DictReader(io.StringIO(z.read('revision_A.csv').decode('utf-8-sig'))))
            self.assertEqual(len(rows), 1)

    def test_excluye_frutas_no_seleccionadas(self):
        self.put('P001', selected='no')
        self.put('P002')
        result = prepare(self.csv, self.images, self.output)
        self.assertEqual(result['piezas'], 1)
        with zipfile.ZipFile(self.output / 'AG036_Revisor_A.zip') as z:
            self.assertNotIn('imagenes/LOTE1_P001_1.png', z.namelist())

    def test_ataulfo_no_cuenta_como_kent(self):
        self.put('M001', product='mango', variety='Ataulfo')
        self.put('T001')
        result = prepare(self.csv, self.images, self.output)
        self.assertEqual(result['por_producto'], {'tomate': 1})

    def test_preview_escapa_rutas_con_espacios_y_numerales(self):
        self.put('P001', rel='vista 1#fruta.png')
        prepare(self.csv, self.images, self.output)
        with zipfile.ZipFile(self.output / 'AG036_Revisor_A.zip') as z:
            self.assertIn('imagenes/vista 1#fruta.png', z.namelist())
            html = z.read('indice.html').decode('utf-8')
            self.assertIn('src="imagenes/vista%201%23fruta.png"', html)

    def test_sin_ninguna_pieza_no_crea_paquetes(self):
        with self.assertRaisesRegex(AuditError, 'No hay piezas elegibles'):
            prepare(self.csv, self.images, self.output)
        self.assertFalse(self.output.exists())

    def test_solo_ataulfo_no_crea_paquetes(self):
        self.put('M001', product='mango', variety='Ataulfo')
        with self.assertRaisesRegex(AuditError, 'No hay piezas elegibles'):
            prepare(self.csv, self.images, self.output)

    def test_sha_que_no_coincide_bloquea(self):
        row = self.put('P001')
        row['sha256_imagen'] = '0' * 64
        self.save()
        with self.assertRaisesRegex(AuditError, 'SHA256 no coincide'):
            prepare(self.csv, self.images, self.output)
        self.assertFalse(self.output.exists())

    def test_no_sobrescribe_paquetes(self):
        self.put('P001')
        prepare(self.csv, self.images, self.output)
        with self.assertRaisesRegex(AuditError, 'No se sobrescribe'):
            prepare(self.csv, self.images, self.output)

    def test_multiples_rubricas_no_comparables_bloqueadas(self):
        self.put('P001', rubric='tomato-ext-v0.2')
        self.put('P002', rubric='tomato-ext-v0.3')
        with self.assertRaisesRegex(AuditError, 'mezclar versiones'):
            prepare(self.csv, self.images, self.output)

    def test_no_autorizacion_comercial_en_paquete(self):
        self.put('P001')
        prepare(self.csv, self.images, self.output)
        with zipfile.ZipFile(self.output / 'AG036_Revisor_A.zip') as z:
            source = z.read('GUIA_REVISION.md').decode('utf-8')
            self.assertIn('no acredita evaluación humana', source)
            self.assertIn('ni infiera', source)

    def test_no_dos_vistas_con_mismo_archivo(self):
        self.put('P001', suffix=1)
        self.put('P001', suffix=1)
        with self.assertRaisesRegex(AuditError, 'fotografía duplicada'):
            prepare(self.csv, self.images, self.output)

    def test_rechaza_ruta_fuera_raiz(self):
        row = self.put('P001')
        row['imagen_relativa'] = '../otra.png'
        self.save()
        with self.assertRaisesRegex(AuditError, 'Ruta insegura'):
            prepare(self.csv, self.images, self.output)

    def test_cli_sin_datos_devuelve_2(self):
        code = main(['--universo', str(self.csv), '--raiz-imagenes', str(self.images),
                     '--directorio-salida', str(self.output)])
        self.assertEqual(code, 2)
        self.assertFalse(self.output.exists())

    def test_no_crea_paquetes_dentro_de_repo(self):
        self.put('P001')
        repo = Path(__file__).resolve().parents[2]
        with self.assertRaisesRegex(AuditError, 'dentro del repositorio'):
            prepare(self.csv, self.images, repo / 'datos_privados_ag036')


if __name__ == '__main__':
    unittest.main()
