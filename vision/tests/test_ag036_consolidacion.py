"""AG-036 Incremento 03: pruebas sintéticas de recepción (NO evidencia humana)."""
import csv
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

from vision.evaluation.ag036.auditar_etiquetado import AuditError, REVIEW_COLS, UNIVERSE_COLS
from vision.evaluation.ag036.consolidar_devoluciones import consolidate, main
from vision.evaluation.ag036.preparar_paquetes_revision import prepare


def csv_write(path, cols, rows):
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)


def csv_read(path):
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


class ConsolidacionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.images = self.work / 'imagenes'
        self.images.mkdir()
        self.universe = self.work / 'universo.csv'
        rows = []
        for i in (1, 2):
            pic = f'P-{i}.png'
            Image.new('RGB', (64, 64), (i*70, i*15, 30)).save(self.images / pic)
            sha = hashlib.sha256((self.images / pic).read_bytes()).hexdigest()
            rows.append(dict(zip(UNIVERSE_COLS, [
                'tomate', 'Roma', 'LOTE-01', f'P-{i}', 'SES-01', pic, sha,
                'tomato-ext-v0.2', 'si', 'selección previa a etiquetas',
            ])))
        csv_write(self.universe, UNIVERSE_COLS, rows)
        self.prep = self.work / 'paquetes'
        prepare(self.universe, self.images, self.prep)
        self.ra = self.work / 'devueltos-A'
        self.rb = self.work / 'devueltos-B'
        self.ra.mkdir()
        self.rb.mkdir()
        for slot, folder in (('A', self.ra), ('B', self.rb)):
            with zipfile.ZipFile(self.prep / f'AG036_Revisor_{slot}.zip') as z:
                folder.joinpath(f'revision_{slot}.csv').write_bytes(z.read(f'revision_{slot}.csv'))
            (folder / 'soportes').mkdir()
        self.out = self.work / 'consolidacion-01'

    def submit(self, slot, piece, grade='E0', state='etiquetada', *,
               reviewer=None, support=None, crit=None, location=None):
        folder = self.ra if slot == 'A' else self.rb
        path = folder / f'revision_{slot}.csv'
        rows = csv_read(path)
        target = next(r for r in rows if r['pieza_id'] == piece)
        target.update({
            'revisor_id': reviewer or f'revisor{slot}',
            'fecha_revision_iso': '2026-11-08T18:00:00-05:00',
            'estado_revision': state,
            'etiqueta_e0_e1_e2': grade if state == 'etiquetada' else '',
            'justificacion': 'Anotación humana simulada SOLO PARA PRUEBA',
            'criterios_rxx': crit if crit is not None else ('R05' if grade in ('E1', 'E2') and state == 'etiquetada' else ''),
            'ubicacion_evidencia': location if location is not None else ('vista 1 izquierda' if grade in ('E1','E2') and state == 'etiquetada' else ''),
            'soporte_relativo': support if support is not None else f'{piece}.txt',
        })
        if target['soporte_relativo']:
            clean = target['soporte_relativo'].removeprefix('soportes/')
            p = folder / 'soportes' / clean
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f'PRUEBA SINTÉTICA {slot} {piece}', encoding='utf-8')
        csv_write(path, REVIEW_COLS, rows)

    def runit(self, **overrides):
        args = dict(preparation=self.prep, universe_csv=self.universe,
                    images_root=self.images, return_a=self.ra, return_b=self.rb,
                    output_dir=self.out)
        args.update(overrides)
        return consolidate(**args)

    def test_blank_forms_do_not_create_labels(self):
        r = self.runit()
        report = json.loads((self.out / 'AG036_auditoria.json').read_text(encoding='utf-8'))
        self.assertEqual(r['filas_A'], 0)
        self.assertEqual(r['piezas_sin_revisar_A'], 2)
        self.assertEqual(report['por_producto']['tomate']['pares_incompletos'], 2)
        self.assertIsNone(report['por_producto']['tomate']['acuerdo_observado'])
        self.assertFalse(report['cierre_total_AG036_acreditado'])

    def test_pair_agreement_and_disagreement(self):
        self.submit('A','P-1','E0'); self.submit('B','P-1','E0')
        self.submit('A','P-2','E1'); self.submit('B','P-2','E2')
        self.runit()
        report = json.loads((self.out / 'AG036_auditoria.json').read_text(encoding='utf-8'))
        item = report['por_producto']['tomate']
        self.assertEqual(item['pares_con_dos_grados'], 2)
        self.assertEqual(item['acuerdo_observado'], .5)
        self.assertEqual(item['discrepancias'], 1)
        self.assertEqual(report['casos_discrepantes'][0]['pieza_id'], 'P-2')
        self.assertIn('P-2', (self.out / 'AG036_auditoria.md').read_text(encoding='utf-8'))

    def test_originals_untouched_and_evidence_isolated(self):
        self.submit('A', 'P-1', 'E1', support='soportes/obs.txt')
        self.submit('B', 'P-1', 'E2', support='obs.txt')
        original_A = (self.ra / 'revision_A.csv').read_bytes()
        original_B = (self.rb / 'revision_B.csv').read_bytes()
        self.runit()
        self.assertEqual((self.out / 'originales/A/revision_A.csv').read_bytes(), original_A)
        self.assertEqual((self.out / 'originales/B/revision_B.csv').read_bytes(), original_B)
        self.assertNotEqual((self.out / 'soportes/A/obs.txt').read_bytes(),
                            (self.out / 'soportes/B/obs.txt').read_bytes())
        self.assertEqual(csv_read(self.out / 'normalizados/revision_A.csv')[0]['soporte_relativo'], 'A/obs.txt')
        self.assertEqual(csv_read(self.out / 'normalizados/revision_B.csv')[0]['soporte_relativo'], 'B/obs.txt')
        self.assertEqual((self.ra / 'revision_A.csv').read_bytes(), original_A)
        self.assertEqual((self.rb / 'revision_B.csv').read_bytes(), original_B)

    def test_no_evaluable_is_not_accuracy(self):
        self.submit('A', 'P-1', state='no_evaluable'); self.submit('B','P-1','E0')
        self.runit()
        item = json.loads((self.out / 'AG036_auditoria.json').read_text(encoding='utf-8'))['por_producto']['tomate']
        self.assertEqual(item['pares_con_algun_no_evaluable'], 1)
        self.assertIsNone(item['kappa_cohen_no_ponderado'])

    def test_changed_piece_id_rejected(self):
        rows = csv_read(self.ra / 'revision_A.csv')
        rows[0]['pieza_id'] = 'IMPOSTOR'
        csv_write(self.ra / 'revision_A.csv', REVIEW_COLS, rows)
        with self.assertRaisesRegex(AuditError, 'cambiaron'):
            self.runit()
        self.assertFalse(self.out.exists())

    def test_removed_row_rejected(self):
        rows = csv_read(self.ra / 'revision_A.csv')
        csv_write(self.ra / 'revision_A.csv', REVIEW_COLS, rows[:1])
        with self.assertRaisesRegex(AuditError, 'eliminaron'):
            self.runit()

    def test_added_duplicate_rejected(self):
        rows = csv_read(self.ra / 'revision_A.csv')
        csv_write(self.ra / 'revision_A.csv', REVIEW_COLS, rows+[rows[0]])
        with self.assertRaisesRegex(AuditError, 'duplicaron'):
            self.runit()

    def test_modified_rubric_rejected(self):
        rows = csv_read(self.ra / 'revision_A.csv')
        rows[0]['rubrica_version'] = 'tomato-ext-v0.99'
        csv_write(self.ra / 'revision_A.csv', REVIEW_COLS, rows)
        with self.assertRaisesRegex(AuditError, 'campos bloqueados'):
            self.runit()

    def test_missing_support_rejected(self):
        self.submit('A', 'P-1')
        (self.ra / 'soportes/P-1.txt').unlink()
        with self.assertRaisesRegex(AuditError, 'ausente'):
            self.runit()

    def test_path_traversal_rejected(self):
        self.submit('A', 'P-1')
        rows = csv_read(self.ra / 'revision_A.csv')
        rows[0]['soporte_relativo'] = '../privado.txt'
        csv_write(self.ra / 'revision_A.csv', REVIEW_COLS, rows)
        with self.assertRaisesRegex(AuditError, 'ruta insegura'):
            self.runit()

    def test_original_package_tamper_rejected(self):
        p = self.prep / 'AG036_Revisor_A.zip'
        with p.open('ab') as f:
            f.write(b'ALTERADO')
        with self.assertRaisesRegex(AuditError, 'SHA256'):
            self.runit()

    def _rewrite_sealed_zip(self, slot, change):
        package = self.prep / f'AG036_Revisor_{slot}.zip'
        with zipfile.ZipFile(package) as archive:
            entries = {name: archive.read(name) for name in archive.namelist() if not name.endswith('/')}
        change(entries)
        with zipfile.ZipFile(package, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, blob in entries.items():
                archive.writestr(name, blob)
        act_path = self.prep / 'AG036_acta_preparacion.json'
        act = json.loads(act_path.read_text(encoding='utf-8'))
        act['sha256_zips'][slot] = hashlib.sha256(package.read_bytes()).hexdigest()
        act_path.write_text(json.dumps(act), encoding='utf-8')

    def test_photo_inside_package_must_match_universe_even_if_acta_is_rehashed(self):
        self._rewrite_sealed_zip('A', lambda items: items.__setitem__('imagenes/P-1.png', b'adulterado'))
        with self.assertRaisesRegex(AuditError, 'foto alterada'):
            self.runit()

    def test_original_prefilled_label_rejected_even_if_zip_rehashed(self):
        def change(items):
            rows = list(csv.DictReader(items['revision_A.csv'].decode('utf-8-sig').splitlines()))
            rows[0]['etiqueta_e0_e1_e2'] = 'E0'
            import io
            dest = io.StringIO()
            writer = csv.DictWriter(dest, fieldnames=REVIEW_COLS)
            writer.writeheader(); writer.writerows(rows)
            items['revision_A.csv'] = dest.getvalue().encode('utf-8-sig')
        self._rewrite_sealed_zip('A', change)
        with self.assertRaisesRegex(AuditError, 'ya tenía evaluaciones'):
            self.runit()

    def test_missing_photo_inside_package_rejected_even_if_rehashed(self):
        self._rewrite_sealed_zip('A', lambda items: items.pop('imagenes/P-2.png'))
        with self.assertRaisesRegex(AuditError, 'fotografías distintas'):
            self.runit()

    def test_universe_tamper_rejected(self):
        with self.universe.open('a') as f:
            f.write('\n')
        with self.assertRaisesRegex(AuditError, 'universo fue cambiado'):
            self.runit()

    def test_image_tamper_rejected(self):
        (self.images / 'P-1.png').write_bytes(b'cambiada')
        with self.assertRaisesRegex(AuditError, 'SHA256'):
            self.runit()

    def test_preexisting_output_rejected(self):
        self.out.mkdir()
        with self.assertRaisesRegex(AuditError, 'ya existe'):
            self.runit()

    def test_duplicate_return_dirs_rejected(self):
        with self.assertRaisesRegex(AuditError, 'carpetas diferentes'):
            self.runit(return_b=self.ra)

    def test_independent_reviewer_ids_enforced(self):
        self.submit('A','P-1', reviewer='persona1')
        self.submit('B','P-1', reviewer='persona1')
        with self.assertRaisesRegex(AuditError, 'revisores distintos'):
            self.runit()

    def test_incomplete_nonempty_review_is_not_discarded(self):
        rows = csv_read(self.ra / 'revision_A.csv')
        rows[0]['revisor_id'] = 'humanoA'
        csv_write(self.ra / 'revision_A.csv', REVIEW_COLS, rows)
        with self.assertRaisesRegex(AuditError, 'fecha sin zona horaria'):
            self.runit()

    def test_wrong_e1_without_criterion_rejected(self):
        self.submit('A','P-1','E1',crit='')
        with self.assertRaisesRegex(AuditError, 'exige criterio'):
            self.runit()

    def test_receipt_provenance_and_not_certified(self):
        self.submit('A','P-1','E0'); self.submit('B','P-1','E0')
        self.runit()
        act = json.loads((self.out / 'AG036_acta_recepcion.json').read_text(encoding='utf-8'))
        self.assertEqual(act['devoluciones']['A']['filas_con_registro'],1)
        self.assertEqual(len(act['devoluciones']['A']['sha256_csv_recibido']),64)
        self.assertFalse(act['autenticidad_e_independencia_humana_verificadas'])
        self.assertFalse(act['cierre_total_AG036_acreditado'])

    def test_repeated_output_never_overwrites(self):
        self.runit()
        prev = (self.out / 'AG036_auditoria.json').read_bytes()
        with self.assertRaisesRegex(AuditError, 'ya existe'):
            self.runit()
        self.assertEqual(prev, (self.out / 'AG036_auditoria.json').read_bytes())

    def test_main_cli_generates_report(self):
        rc = main(['--preparacion', str(self.prep), '--universo', str(self.universe),
                   '--raiz-imagenes', str(self.images), '--devolucion-a', str(self.ra),
                   '--devolucion-b', str(self.rb), '--directorio-salida', str(self.out)])
        self.assertEqual(rc, 0)
        self.assertTrue((self.out/'AG036_acta_recepcion.json').is_file())
        self.assertEqual(main(['--preparacion', str(self.prep), '--universo', str(self.universe),
                               '--raiz-imagenes', str(self.images), '--devolucion-a', str(self.ra),
                               '--devolucion-b', str(self.rb), '--directorio-salida', str(self.out)]), 2)


if __name__ == '__main__':
    unittest.main()
