"""Pruebas de inventario técnico. No acreditan la procedencia de imágenes."""
import csv
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from vision.evaluation.ag036.auditar_etiquetado import AuditError
from vision.evaluation.ag036.inventariar_fotografias import inventory, main


class InventarioTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base / 'imagenes'
        self.root.mkdir()
        self.csv = self.base / 'inventario.csv'

    def image(self, name='img01.png', color=(14, 33, 42)):
        path = self.root / name
        path.parent.mkdir(exist_ok=True, parents=True)
        Image.new('RGB', (50, 40), color).save(path)
        return path

    def test_inventario_no_fabrica_identidades(self):
        self.image()
        self.image('sub/img02.jpg', (120, 100, 30))
        result = inventory(self.root, self.csv)
        self.assertEqual(result['fotografias'], 2)
        with self.csv.open(encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))
        self.assertEqual({r['imagen_relativa'] for r in rows}, {'img01.png', 'sub/img02.jpg'})
        self.assertTrue(all(len(r['sha256_imagen']) == 64 for r in rows))
        self.assertTrue(all(r['seleccion_doble'] == 'no' for r in rows))
        for field in ('producto', 'variedad_declarada', 'lote_id', 'pieza_id', 'sesion_id', 'rubrica_version'):
            self.assertTrue(all(r[field] == '' for r in rows))

    def test_no_acepta_archivo_corrupto(self):
        (self.root / 'invalida.jpg').write_bytes(b'no-soy-una-imagen')
        with self.assertRaisesRegex(AuditError, 'Imagen ilegible'):
            inventory(self.root, self.csv)
        self.assertFalse(self.csv.exists())

    def test_no_inventa_fotos_si_carpeta_esta_vacia(self):
        with self.assertRaisesRegex(AuditError, 'No hay fotografías'):
            inventory(self.root, self.csv)
        self.assertFalse(self.csv.exists())

    def test_no_sobrescribe(self):
        self.image()
        inventory(self.root, self.csv)
        before = self.csv.read_bytes()
        with self.assertRaisesRegex(AuditError, 'no sobrescribir'):
            inventory(self.root, self.csv)
        self.assertEqual(before, self.csv.read_bytes())

    def test_archivos_identicos_se_reportan_sin_asignarlos_a_piezas(self):
        path = self.image()
        (self.root / 'copia.png').write_bytes(path.read_bytes())
        result = inventory(self.root, self.csv)
        self.assertEqual(result['imagenes_contenido_repetido'], 1)
        self.assertEqual(result['fotografias'], 2)

    def test_no_inventario_csv_dentro_de_git(self):
        self.image()
        repo = Path(__file__).resolve().parents[2]
        with self.assertRaisesRegex(AuditError, 'fuera del repositorio'):
            inventory(self.root, repo / 'inventario-privado.csv')

    def test_main_sin_fotografias_devuelve_error(self):
        self.assertEqual(main(['--directorio-imagenes', str(self.root), '--salida-csv', str(self.csv)]), 2)
        self.assertFalse(self.csv.exists())


if __name__ == '__main__':
    unittest.main()
