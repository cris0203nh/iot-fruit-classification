"""AGROP-40: pruebas de software con formas sintéticas, NO métricas de precisión agronómica."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from vision.src.mango_pipeline import evaluate_manifest
from vision.src.surface_analysis import propose_surface_regions
from vision.src.surface_masks import InvalidSurfaceSelection, describe_surface_masks, save_mask_preview


class SurfaceMaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def image(self, count=2):
        image = Image.new('RGB', (480, 320), (150, 150, 150))
        draw = ImageDraw.Draw(image)
        for i in range(count):
            x = 50 + i * 230
            draw.ellipse((x, 55, x + 160, 280), fill=(125, 141, 44))
        return image

    def manifest(self, name='mango.png'):
        self.image().save(self.root / name)
        return {
            'experiment_id': 'SINTETICO',
            'piece': {'lot_id': 'T', 'piece_id': 'X', 'product': 'mango', 'variety_declared': 'Kent'},
            'coverage_verified': None,
            'images': [{
                'image_id': 'I-SINTETICO', 'view': 'vista-1', 'path': name,
                'quality': {'focus_ok': True, 'lighting_ok': True, 'unoccluded': True},
                'roi_xywh': None, 'roi_verified': False,
            }],
            'weight': None,
        }

    def test_dos_mascaras_separadas_sin_unir_vistas(self):
        image = self.image()
        proposal = propose_surface_regions(image)
        output = describe_surface_masks(image, proposal)
        self.assertEqual(proposal['status'], 'ambiguous_multiple_regions')
        self.assertEqual(output['status'], 'pending_operator_selection')
        self.assertEqual(len(output['segments']), 2)
        self.assertEqual(output['assignment_of_regions_to_piece'], 'not_verified')
        self.assertTrue(output['requires_independent_validation'])

    def test_mascaras_excluyen_el_fondo_del_calculo_rgb(self):
        image = self.image(1)
        proposal = propose_surface_regions(image)
        output = describe_surface_masks(image, proposal)
        segment = output['segments'][0]
        self.assertEqual(segment['masked_median_rgb'], [125, 141, 44])
        self.assertLess(segment['mask_fill_fraction_of_bbox'], 0.92)
        self.assertGreater(segment['mask_fill_fraction_of_bbox'], 0.4)
        self.assertEqual(segment['masked_rgb_p10'], [125, 141, 44])
        self.assertEqual(segment['masked_rgb_p90'], [125, 141, 44])
        self.assertFalse(segment['selected_by_operator'])

    def test_seleccion_manual_documentada_no_confirma_identidad_ni_etiqueta(self):
        manifest = self.manifest()
        manifest['images'][0]['surface_selection'] = {
            'candidate_indices': [1, 2],
            'reviewed_by_operator': True,
            'review_note': 'Se revisaron dos regiones en una foto compuesta; identidad pendiente.',
        }
        output = evaluate_manifest(manifest, self.root)
        report = output['images'][0]['mask_analysis']
        self.assertEqual(report['status'], 'operator_selected_provisional_masks')
        self.assertEqual(report['selected_candidate_indices'], [1, 2])
        self.assertTrue(all(segment['selected_by_operator'] for segment in report['segments']))
        self.assertEqual(report['assignment_of_regions_to_piece'], 'not_verified')
        self.assertIsNone(output['visual_label'])
        for code in ('R03', 'R04', 'R05', 'R06'):
            self.assertEqual(output['criteria'][code]['presence'], 'no_determinable')

    def test_ausencia_de_seleccion_mantiene_candidatos_no_confirmados(self):
        out = evaluate_manifest(self.manifest(), self.root)
        mask = out['criteria']['R07']['provisional_surface_masks'][0]
        self.assertEqual(mask['status'], 'pending_operator_selection')
        self.assertFalse(mask['operator_selection_declared'])
        self.assertIsNone(out['visual_label'])

    def test_indices_fuera_de_rango_rechazados(self):
        manifest = self.manifest()
        manifest['images'][0]['surface_selection'] = {'candidate_indices': [9], 'reviewed_by_operator': True, 'review_note': 'Revisado'}
        with self.assertRaises(InvalidSurfaceSelection):
            evaluate_manifest(manifest, self.root)

    def test_seleccion_duplicada_rechazada(self):
        manifest = self.manifest()
        manifest['images'][0]['surface_selection'] = {'candidate_indices': [1, 1], 'reviewed_by_operator': True, 'review_note': 'Revisado'}
        with self.assertRaises(InvalidSurfaceSelection):
            evaluate_manifest(manifest, self.root)

    def test_sin_nota_o_confirmacion_rechazado(self):
        manifest = self.manifest()
        for params in ({'candidate_indices': [1], 'reviewed_by_operator': False, 'review_note': 'Revisado'},
                       {'candidate_indices': [1], 'reviewed_by_operator': True, 'review_note': ' '}):
            manifest['images'][0]['surface_selection'] = params
            with self.assertRaises(InvalidSurfaceSelection):
                evaluate_manifest(manifest, self.root)

    def test_fondo_sin_componentes_no_fabrica_mascara(self):
        image = Image.new('RGB', (480, 320), (140, 140, 140))
        out = describe_surface_masks(image, propose_surface_regions(image))
        self.assertEqual(out['status'], 'unavailable')
        self.assertEqual(out['segments'], [])

    def test_mascara_png_independiente_no_modifica_original(self):
        source = self.root / 'fuente.png'
        output = self.root / 'diagnostico.png'
        self.image().save(source)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        proposal = propose_surface_regions(Image.open(source))
        save_mask_preview(source, proposal, output)
        self.assertTrue(output.is_file())
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), digest)
        self.assertNotEqual(Image.open(output).getpixel((0, 0)), Image.open(output).getpixel((135, 135)))
        with self.assertRaises(ValueError):
            save_mask_preview(source, proposal, source)

    def test_cli_mascara_y_json_reproducibles(self):
        manifest = self.manifest()
        m = self.root / 'input.json'
        out = self.root / 'output.json'
        m.write_text(json.dumps(manifest), encoding='utf-8')
        args = [sys.executable, '-m', 'vision.src.mango_pipeline', '--manifest', str(m),
                '--output', str(out), '--mask-preview-dir', str(self.root / 'mascaras')]
        project = Path(__file__).resolve().parents[2]
        subprocess.run(args, cwd=project, check=True, capture_output=True)
        first = out.read_bytes()
        pics = list((self.root / 'mascaras').glob('*.png'))
        self.assertEqual(len(pics), 1)
        before = pics[0].read_bytes()
        subprocess.run(args, cwd=project, check=True, capture_output=True)
        self.assertEqual(out.read_bytes(), first)
        self.assertEqual(pics[0].read_bytes(), before)
        self.assertIsNone(json.loads(first)['visual_label'])

    def test_mascaras_no_alteran_peso_ni_estado_de_revision(self):
        manifest = self.manifest()
        manifest['weight'] = {'grams': 600, 'stable': True, 'calibrated': True, 'uncertainty_g': 0}
        result = evaluate_manifest(manifest, self.root)
        self.assertEqual(result['criteria']['R02']['reference'], 'C')
        self.assertEqual(result['visual_status'], 'pendiente_revision')
        self.assertFalse(result['requires_human_review'] is False)
        self.assertIsNone(result['visual_label'])


if __name__ == '__main__':
    unittest.main()
