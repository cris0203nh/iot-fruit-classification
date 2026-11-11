"""Pruebas sintéticas de SOFTWARE: no son evaluaciones humanas ni evidencia agronómica."""
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from vision.evaluation.ag036.auditar_etiquetado import (AuditError, audit, kappa, markdown, main)

UC = ['producto', 'variedad_declarada', 'lote_id', 'pieza_id', 'sesion_id', 'imagen_relativa',
      'sha256_imagen', 'rubrica_version', 'seleccion_doble', 'criterio_seleccion']
RC = ['producto', 'lote_id', 'pieza_id', 'revisor_id', 'fecha_revision_iso', 'rubrica_version',
      'estado_revision', 'etiqueta_e0_e1_e2', 'justificacion', 'criterios_rxx', 'ubicacion_evidencia', 'soporte_relativo']
AC = ['producto', 'lote_id', 'pieza_id', 'estado_conciliacion', 'etiqueta_final',
      'revisor_arbitro', 'fecha_iso', 'justificacion', 'soporte_relativo', 'rubrica_nueva_propuesta']


def save_csv(path, cols, rows):
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)


class ConcordanciaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.images = self.root / 'imagenes'
        self.supports = self.root / 'soportes'
        self.images.mkdir()
        self.supports.mkdir()
        (self.supports / 'rev.txt').write_text('Registro de prueba sintética', encoding='utf-8')
        self.u, self.a, self.b, self.adj = (self.root / x for x in ['universo.csv', 'a.csv', 'b.csv', 'conc.csv'])
        self.universe, self.ra, self.rb, self.conc = [], [], [], []
        self.dump()

    def dump(self):
        save_csv(self.u, UC, self.universe)
        save_csv(self.a, RC, self.ra)
        save_csv(self.b, RC, self.rb)
        save_csv(self.adj, AC, self.conc)

    def put(self, pid, *, product='tomate', variety='Roma', selected='si', session=None, suffix=0, lot='L-PRUEBA'):
        name = f'{lot}_{pid}_{suffix}.png'
        # Valores diferentes: fotografías de prueba y no copias de piezas diferentes
        num = sum(ord(x) for x in lot + pid) + suffix
        Image.new('RGB', (64, 64), ((num * 13) % 256, (num * 11) % 256, (num * 7) % 256)).save(self.images / name)
        sha = hashlib.sha256((self.images / name).read_bytes()).hexdigest()
        self.universe.append(dict(zip(UC, [product, variety, lot, pid, session or 'S-' + lot + '-' + pid, name,
                                           sha, 'kent-ext-v0.5' if product == 'mango' else 'tomato-ext-v0.1',
                                           selected, 'muestreo piloto predefinido' if selected == 'si' else ''])))
        self.dump()
        return self.universe[-1]

    def review(self, pid, grade, *, slot='A', product='tomate', reviewer=None,
               date='2026-11-08T14:00:00-05:00', state=None, support='rev.txt', lot='L-PRUEBA'):
        state = state or ('etiquetada' if grade in ('E0', 'E1', 'E2') else grade)
        if state != 'etiquetada':
            grade = ''
        row = dict(zip(RC, [product, lot, pid, reviewer or ('humanoA' if slot == 'A' else 'humanoB'),
                            date, 'kent-ext-v0.5' if product == 'mango' else 'tomato-ext-v0.1',
                            state, grade, 'Inspección según rúbrica' if state != 'pendiente' else '',
                            ('R03' if product == 'mango' else 'R05') if grade in ('E1', 'E2') else '',
                            'vista-1, centro' if grade in ('E1', 'E2') else '',
                            support if state != 'pendiente' else '']))
        (self.ra if slot == 'A' else self.rb).append(row)
        self.dump()
        return row

    def runaudit(self, adj=False):
        return audit(self.u, self.a, self.b, self.images, self.supports, self.adj if adj else None)

    def test_blank_templates_block_and_do_not_invent_kappa(self):
        report = self.runaudit()
        self.assertEqual(report['por_producto']['mango']['estado'], 'sin_subconjunto_seleccionado')
        self.assertIsNone(report['por_producto']['tomate']['kappa_cohen_no_ponderado'])
        self.assertFalse(report['cierre_total_AG036_acreditado'])

    def test_coverage_and_disagreements(self):
        for p in ('p1', 'p2', 'p3', 'p4'):
            self.put(p)
        self.review('p1', 'E0'); self.review('p1', 'E0', slot='B')
        self.review('p2', 'E1'); self.review('p2', 'E2', slot='B')
        self.review('p3', 'E2')
        d = self.runaudit()['por_producto']['tomate']
        self.assertEqual((d['piezas_elegibles'], d['pares_con_dos_grados'], d['acuerdos_exactos']), (4, 2, 1))
        self.assertEqual(d['pares_incompletos'], 2)
        self.assertEqual(d['cobertura_doble_grado_sobre_seleccionadas'], .5)
        self.assertEqual(d['discrepancias'], 1)
        self.assertEqual(self.runaudit()['casos_discrepantes'][0]['pieza_id'], 'p2')

    def test_kappa_independent_from_accuracy(self):
        matrix = {x: {y: 0 for y in ('E0', 'E1', 'E2')} for x in ('E0', 'E1', 'E2')}
        matrix['E0']['E0'] = 1
        matrix['E0']['E1'] = 1
        matrix['E1']['E1'] = 2
        self.assertAlmostEqual(kappa(matrix), .5)

    def test_kappa_degenerate_is_null(self):
        matrix = {x: {y: 0 for y in ('E0', 'E1', 'E2')} for x in ('E0', 'E1', 'E2')}
        matrix['E0']['E0'] = 5
        self.assertIsNone(kappa(matrix))

    def test_mango_ataulfo_not_in_eligible_universe(self):
        self.put('ata', product='mango', variety='Ataulfo')
        self.put('kent', product='mango', variety='Kent')
        d = self.runaudit()['por_producto']['mango']
        self.assertEqual(d['piezas_elegibles'], 1)
        self.assertEqual(d['piezas_seleccionadas_para_doble_revision'], 1)

    def test_unselected_piece_cannot_be_reviewed(self):
        self.put('p1', selected='no')
        self.review('p1', 'E0')
        with self.assertRaisesRegex(AuditError, 'no seleccionada'):
            self.runaudit()

    def test_same_reviewer_rejected(self):
        self.put('p1')
        self.review('p1', 'E1', reviewer='personaX')
        self.review('p1', 'E1', slot='B', reviewer='personaX')
        with self.assertRaisesRegex(AuditError, 'distintos'):
            self.runaudit()

    def test_reviewer_identity_fixed_per_file(self):
        self.put('p1'); self.put('p2')
        self.review('p1', 'E0', reviewer='personaA')
        self.review('p2', 'E1', reviewer='personaB')
        with self.assertRaisesRegex(AuditError, 'único identificador'):
            self.runaudit()

    def test_pending_not_assumed_to_be_label(self):
        self.put('p1')
        self.review('p1', 'pendiente', state='pendiente')
        self.review('p1', 'E0', slot='B')
        d = self.runaudit()['por_producto']['tomate']
        self.assertEqual(d['pares_incompletos'], 1)
        self.assertIsNone(d['acuerdo_observado'])

    def test_no_evaluable_does_not_enter_grade_kappa(self):
        self.put('p1')
        self.review('p1', 'no_evaluable'); self.review('p1', 'E0', slot='B')
        d = self.runaudit()['por_producto']['tomate']
        self.assertEqual(d['pares_con_algun_no_evaluable'], 1)
        self.assertEqual(d['discrepancias'], 1)
        self.assertIsNone(d['kappa_cohen_no_ponderado'])

    def test_two_no_evaluable_are_counted_separately(self):
        self.put('p1')
        self.review('p1', 'no_evaluable'); self.review('p1', 'no_evaluable', slot='B')
        d = self.runaudit()['por_producto']['tomate']
        self.assertEqual(d['pares_con_algun_no_evaluable'], 1)
        self.assertEqual(d['pares_completos_incluyendo_no_evaluable'], 1)
        self.assertEqual(d['ambos_no_evaluables'], 1)
        self.assertEqual(d['cobertura_doble_revision_sobre_seleccionadas'], 1.0)
        self.assertEqual(d['discrepancias'], 0)

    def test_sha_mismatch_rejected(self):
        row = self.put('p1'); row['sha256_imagen'] = '0' * 64; self.dump()
        with self.assertRaisesRegex(AuditError, 'SHA256 no coincide'):
            self.runaudit()

    def test_corrupted_png_rejected(self):
        row = self.put('p1')
        (self.images / row['imagen_relativa']).write_bytes(b'not png')
        row['sha256_imagen'] = hashlib.sha256(b'not png').hexdigest()
        self.dump()
        with self.assertRaisesRegex(AuditError, 'imagen inválida'):
            self.runaudit()

    def test_duplicate_hash_between_pieces_rejected(self):
        self.put('p1'); row = self.put('p2')
        (self.images / row['imagen_relativa']).write_bytes((self.images / 'L-PRUEBA_p1_0.png').read_bytes())
        row['sha256_imagen'] = hashlib.sha256((self.images / row['imagen_relativa']).read_bytes()).hexdigest()
        self.dump()
        with self.assertRaisesRegex(AuditError, 'misma imagen'):
            self.runaudit()

    def test_duplicate_views_one_piece_allowed(self):
        self.put('p1', suffix=0)
        self.put('p1', suffix=1)
        d = self.runaudit()
        self.assertEqual(d['universo']['filas_vistas'], 2)
        self.assertEqual(d['por_producto']['tomate']['piezas_elegibles'], 1)

    def test_session_conflict_not_allowed_as_different_selection(self):
        self.put('p1', selected='si', suffix=0)
        self.put('p1', selected='no', suffix=1)
        with self.assertRaisesRegex(AuditError, 'contradictorios'):
            self.runaudit()

    def test_invalid_rubric_rejected(self):
        row = self.put('p1'); row['rubrica_version'] = 'kent-ext-v0.5'; self.dump()
        with self.assertRaisesRegex(AuditError, 'rúbrica'):
            self.runaudit()

    def test_date_without_timezone_rejected(self):
        self.put('p1'); self.review('p1', 'E0', date='2026-11-08T12:00:00')
        with self.assertRaisesRegex(AuditError, 'sin zona horaria'):
            self.runaudit()

    def test_support_missing_rejected(self):
        self.put('p1'); self.review('p1', 'E0', support='no-existe.txt')
        with self.assertRaisesRegex(AuditError, 'ausente'):
            self.runaudit()

    def test_path_traversal_rejected(self):
        row = self.put('p1'); row['imagen_relativa'] = '../fuera.png'; self.dump()
        with self.assertRaisesRegex(AuditError, 'Ruta insegura'):
            self.runaudit()

    def test_adjudication_third_reviewer_and_resolve(self):
        self.put('p1')
        self.review('p1', 'E0'); self.review('p1', 'E1', slot='B')
        self.conc.append(dict(zip(AC, ['tomate', 'L-PRUEBA', 'p1', 'resuelto', 'E1', 'arbitro3',
                                       '2026-11-08T16:00:00-05:00', 'Criterio contrastado', 'rev.txt', ''])))
        self.dump()
        d = self.runaudit(adj=True)
        self.assertEqual(d['conciliacion']['resueltas_documentalmente'], 1)
        self.assertEqual(d['casos_discrepantes'][0]['conciliacion'], 'resuelto')
        self.assertFalse(d['cierre_total_AG036_acreditado'])

    def test_adjudication_same_reviewer_rejected(self):
        self.put('p1')
        self.review('p1', 'E0'); self.review('p1', 'E1', slot='B')
        self.conc.append(dict(zip(AC, ['tomate', 'L-PRUEBA', 'p1', 'resuelto', 'E1', 'humanoA',
                                       '2026-11-08T16:00:00-05:00', 'Criterio', 'rev.txt', ''])))
        self.dump()
        with self.assertRaisesRegex(AuditError, 'árbitro diferente'):
            self.runaudit(adj=True)

    def test_adjudication_cannot_create_new_conflict(self):
        self.put('p1'); self.review('p1', 'E0'); self.review('p1', 'E0', slot='B')
        self.conc.append(dict(zip(AC, ['tomate', 'L-PRUEBA', 'p1', 'pendiente', '', '', '', '', '', ''])))
        self.dump()
        with self.assertRaisesRegex(AuditError, 'no discrepante'):
            self.runaudit(adj=True)

    def test_proposed_rubric_does_not_change_official(self):
        self.put('p1'); self.review('p1', 'E0'); self.review('p1', 'E1', slot='B')
        self.conc.append(dict(zip(AC, ['tomate', 'L-PRUEBA', 'p1', 'ajuste_rubrica_propuesto', '', '', '',
                                       'Aclarar umbral', '', 'tomato-ext-v0.2-propuesta'])))
        self.dump()
        d = self.runaudit(adj=True)
        self.assertEqual(d['conciliacion']['ajustes_rubrica_propuestos'], 1)
        self.assertFalse(d['rubricas_aprobadas_verificadas_por_software'])

    def test_same_piece_id_different_lots_are_distinct(self):
        self.put('P-001', lot='L-1')
        self.put('P-001', lot='L-2')
        self.review('P-001', 'E0', lot='L-1')
        self.review('P-001', 'E1', lot='L-1', slot='B')
        self.review('P-001', 'E2', lot='L-2')
        self.review('P-001', 'E2', lot='L-2', slot='B')
        report = self.runaudit()
        d = report['por_producto']['tomate']
        self.assertEqual(d['piezas_elegibles'], 2)
        self.assertEqual(d['pares_con_dos_grados'], 2)
        self.assertEqual(d['discrepancias'], 1)
        self.assertEqual(report['casos_discrepantes'][0]['lote_id'], 'L-1')

    def test_ag035_primera_segunda_is_not_accepted_as_visual_grade(self):
        self.put('p1')
        row = self.review('p1', 'E0')
        row['etiqueta_e0_e1_e2'] = 'primera'
        self.dump()
        with self.assertRaisesRegex(AuditError, 'etiqueta'):
            self.runaudit()

    def test_no_claim_automated_equivalence_ag035(self):
        report = self.runaudit()
        self.assertEqual(report['equivalencia_con_primera_segunda_AG035'], 'NO ESTABLECIDA')
        self.assertFalse(report['rubricas_aprobadas_verificadas_por_software'])

    def test_E1_needs_observable_criterion_and_evidence_location(self):
        self.put('p1')
        row = self.review('p1', 'E1')
        row['criterios_rxx'] = ''
        self.dump()
        with self.assertRaisesRegex(AuditError, 'exige criterio'):
            self.runaudit()

    def test_criterion_code_is_limited_by_product(self):
        self.put('p1', product='mango', variety='Kent')
        row = self.review('p1', 'E2', product='mango')
        row['criterios_rxx'] = 'R09'
        self.dump()
        with self.assertRaisesRegex(AuditError, 'criterio Rxx inválido'):
            self.runaudit()

    def test_mixed_rubric_versions_block_aggregated_kappa(self):
        self.put('p1')
        row = self.put('p2')
        row['rubrica_version'] = 'tomato-ext-v0.2'
        self.dump()
        with self.assertRaisesRegex(AuditError, 'no combinar piezas'):
            self.runaudit()

    def test_reports_pending_cases_without_inventing_agreement(self):
        self.put('p1')
        self.review('p1', 'E0')
        report = self.runaudit()
        cases = report['por_producto']['tomate']['casos_pendientes_de_par']
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]['estado_B'], 'sin_revision')
        self.assertIsNone(report['por_producto']['tomate']['acuerdo_observado'])
        self.assertIn('Pares pendientes', markdown(report))

    def test_md_contains_result_and_limit(self):
        r = self.runaudit()
        text = markdown(r)
        self.assertIn('No calculable', text)
        self.assertIn('AG-030/AG-035', text)

    def test_cli_creates_files_not_overwriting(self):
        path = self.root / 'reporte.json'
        args = ['--universo', str(self.u), '--revision-a', str(self.a), '--revision-b', str(self.b),
                '--raiz-imagenes', str(self.images), '--raiz-soportes', str(self.supports), '--salida', str(path)]
        self.assertEqual(main(args), 0)
        self.assertTrue(path.with_suffix('.md').exists())
        first = path.read_bytes()
        self.assertEqual(main(args), 2)
        self.assertEqual(first, path.read_bytes())


if __name__ == '__main__':
    unittest.main()
