"""Pruebas sobre patrones sintéticos. NO certifican precisión con mangos reales."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from vision.src.mango_pipeline import evaluate_manifest
from vision.src.surface_analysis import propose_surface_regions, save_candidate_preview


class SurfaceAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def image(self, count=1, background=(135, 135, 135)):
        im = Image.new('RGB', (480, 320), background)
        draw = ImageDraw.Draw(im)
        for i in range(count):
            x = 50 + i * 230
            draw.ellipse((x, 55, x + 160, 280), fill=(112, 151, 38))
        return im

    def test_una_region_cromatica_con_fondo_neutro(self):
        result = propose_surface_regions(self.image())
        self.assertEqual(result['status'], 'single_candidate_unverified')
        self.assertEqual(result['candidate_count'], 1)
        self.assertFalse(result['candidates'][0]['verified_as_mango'])
        self.assertGreater(result['candidates'][0]['coverage_fraction_of_image'], 0)
        self.assertTrue(result['requires_manual_confirmation'])

    def test_dos_regiones_no_son_dos_vistas_confirmadas(self):
        result = propose_surface_regions(self.image(2))
        self.assertEqual(result['status'], 'ambiguous_multiple_regions')
        self.assertEqual(result['candidate_count'], 2)
        self.assertIn('varias_regiones', result['reason'])

    def test_fondo_saturado_no_forzar_segmentacion(self):
        result = propose_surface_regions(Image.new('RGB', (480, 320), (20, 150, 30)))
        self.assertEqual(result['status'], 'background_not_supported')
        self.assertEqual(result['candidate_count'], 0)

    def test_fondo_neutro_sin_region_coloreada(self):
        result = propose_surface_regions(Image.new('RGB', (480, 320), (130, 130, 130)))
        self.assertEqual(result['status'], 'no_candidate')
        self.assertEqual(result['candidate_count'], 0)

    def test_vista_de_diagnostico_no_modifica_fuente(self):
        source = self.root / 'fuente.png'
        out = self.root / 'vista.png'
        self.image(2).save(source)
        before = source.read_bytes()
        analysis = propose_surface_regions(self.image(2))
        save_candidate_preview(source, analysis, out)
        self.assertTrue(out.exists())
        self.assertEqual(source.read_bytes(), before)
        with self.assertRaises(ValueError):
            save_candidate_preview(source, analysis, source)

    def test_pipeline_preserva_sin_clasificar_defectos(self):
        photo = self.root / 'realizacion_sintetica.png'
        self.image(2).save(photo)
        manifest = {
            'experiment_id': 'test-propuesta',
            'piece': {'lot_id': 'TEST', 'piece_id': 'T01', 'product': 'mango', 'variety_declared': 'Kent'},
            'coverage_verified': None,
            'images': [{
                'image_id': 'I-TEST', 'view': 'vista-1', 'path': 'realizacion_sintetica.png',
                'quality': {'focus_ok': True, 'lighting_ok': True, 'unoccluded': True},
                'roi_xywh': [85, 100, 50, 120], 'roi_verified': True,
            }],
            'weight': None,
        }
        result = evaluate_manifest(manifest, self.root)
        self.assertEqual(result['visual_status'], 'pendiente_revision')
        self.assertIsNone(result['visual_label'])
        self.assertEqual(result['criteria']['R07']['surface_proposals'][0]['candidate_count'], 2)
        self.assertEqual(result['criteria']['R02']['status'], 'pendiente')
        for rule in ('R03', 'R04', 'R05', 'R06'):
            self.assertEqual(result['criteria'][rule]['presence'], 'no_determinable')

    def test_clasificacion_no_activa_por_contraste(self):
        source = self.root / 'artificial.png'
        self.image(2).save(source)
        analysis = propose_surface_regions(Image.open(source))
        self.assertNotIn('defect', json.dumps(analysis).lower().replace('no detectan defectos',''))
        self.assertFalse(any(x['verified_as_mango'] for x in analysis['candidates']))

    def test_cli_preview_y_resultado_deterministas(self):
        p = self.root / 'estudio.png'
        self.image(2).save(p)
        manifest = {
            'piece': {'lot_id': 'T', 'piece_id': 'M', 'product': 'mango', 'variety_declared': 'Kent'},
            'coverage_verified': None,
            'images': [{'path': str(p), 'image_id': 'I-002', 'view': 'vista-1',
                        'quality': {'focus_ok': True, 'lighting_ok': True, 'unoccluded': True},
                        'roi_xywh': None, 'roi_verified': False}],
        }
        m = self.root / 'manifiesto.json'
        output = self.root / 'out.json'
        m.write_text(json.dumps(manifest), encoding='utf-8')
        cmd = [sys.executable, '-m', 'vision.src.mango_pipeline', '--manifest', str(m),
               '--output', str(output), '--preview-dir', str(self.root / 'vistas')]
        base = Path(__file__).resolve().parents[2]
        subprocess.run(cmd, cwd=base, check=True, capture_output=True, text=True)
        first = output.read_bytes()
        pngs = list((self.root / 'vistas').glob('*.png'))
        self.assertEqual(len(pngs), 1)
        subprocess.run(cmd, cwd=base, check=True, capture_output=True, text=True)
        self.assertEqual(first, output.read_bytes())


if __name__ == '__main__':
    unittest.main()
