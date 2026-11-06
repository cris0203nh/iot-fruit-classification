"""Incremento 12: fixtures sintéticos para contratos, no imágenes etiquetadas reales."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from vision.evaluation.agrop42.preparar_revision_calidad_ag034 import (
    COLUMNS, ReviewError, _csv_bytes, _csv_read, auditar,
    generar_plantilla, informe_md, main, verificar,
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_csv(path: Path, rows: list[dict]) -> None:
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(out.getvalue(), encoding='utf-8')


class RevisionCalidadAG034Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.zip = self.base / 'dataset.zip'
        self.ia = self.base / 'ia.csv'
        self.revision = self.base / 'decision.csv'
        self.source_rows = []
        with ZipFile(self.zip, 'w') as z:
            trace = []
            for prod, plural in (('mango', 'mangos'), ('tomate', 'tomates')):
                pid = ('MANGO' if prod == 'mango' else 'TOMATE') + '_01'
                for view in (1, 2, 3):
                    file = f'{plural}/{pid}/vista_{view:02d}.jpg'
                    b = f'sintetico_{file}'.encode('utf-8')
                    sha = digest(b)
                    z.writestr(file, b)
                    trace.append({'archivo': file, 'id_ejemplar': pid, 'vista': view, 'sha256': sha})
                    self.source_rows.append({
                        'producto': prod, 'id_ejemplar_fuente': pid, 'vista': str(view),
                        'archivo_origen': file, 'sha256': sha,
                        'revision_visual_mascara_IA': 'sin_mascara' if view == 1 else 'compatible_visual_provisional',
                        'observaciones_visual_IA': 'observacion sintética de prueba',
                        'es_mango_kent': 'no; Ataulfo según fuente' if prod == 'mango' else 'no_aplica',
                        'aprobacion_operador_o_experto': 'pendiente',
                        'etiqueta_E0_E1_E2_acreditada': '',
                    })
            out = io.StringIO(newline='')
            writer = csv.DictWriter(out, fieldnames=list(trace[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(trace)
            z.writestr('trazabilidad.csv', out.getvalue().encode('utf-8'))
        write_csv(self.ia, self.source_rows)
        blob, _ = generar_plantilla(self.zip, self.ia)
        self.revision.write_bytes(blob)

    def rows(self):
        return _csv_read(self.revision.read_bytes(), 'decisiones')

    def replace(self, rows):
        self.revision.write_bytes(_csv_bytes(rows))

    def test_plantilla_una_fila_por_ejemplar_tres_vistas(self):
        blob, info = generar_plantilla(self.zip, self.ia)
        rows = _csv_read(blob, 'plantilla')
        self.assertEqual(len(rows), 2)
        self.assertEqual(info['vistas'], 6)
        self.assertEqual(info['ejemplares_declarados'], 2)
        self.assertEqual([r['vistas_declaradas'] for r in rows], ['3', '3'])

    def test_plantilla_no_acredita_ninguna_etiqueta(self):
        rows = self.rows()
        self.assertTrue(all(r['estado_revision'] == 'pendiente' for r in rows))
        self.assertTrue(all(not r['etiqueta_e0_e1_e2'] and not r['revisor_id'] for r in rows))

    def test_plantilla_determinista(self):
        b1, _ = generar_plantilla(self.zip, self.ia)
        b2, _ = generar_plantilla(self.zip, self.ia)
        self.assertEqual(b1, b2)

    def test_auditoria_pendiente_bloquea_entrenamiento(self):
        report, _ = auditar(self.zip, self.ia, self.revision)
        self.assertEqual(report['estado'], 'pendiente_de_validacion_externa')
        self.assertEqual(report['revision']['mango']['pendientes'], 1)
        self.assertEqual(report['revision']['tomate']['pendientes'], 1)
        self.assertEqual(report['metricas_e0_e1_e2'], None)
        self.assertFalse(report['entrenamiento_comercial_autorizado'])

    def test_sha_cambiado_bloquea(self):
        rows = self.rows()
        rows[0]['sha256_vistas'] = '0' * 64
        self.replace(rows)
        report, _ = auditar(self.zip, self.ia, self.revision)
        self.assertEqual(report['estado'], 'bloqueado_por_integridad')

    def test_falta_una_fila_bloquea(self):
        self.replace(self.rows()[:-1])
        report, _ = auditar(self.zip, self.ia, self.revision)
        self.assertTrue(report['errores_integridad'])

    def test_fila_repetida_bloquea(self):
        rows = self.rows()
        rows.append(dict(rows[0]))
        self.replace(rows)
        report, _ = auditar(self.zip, self.ia, self.revision)
        self.assertTrue(report['errores_integridad'])

    def test_etiqueta_pendiente_rechazada(self):
        rows = self.rows()
        rows[0]['etiqueta_e0_e1_e2'] = 'E0'
        self.replace(rows)
        report, _ = auditar(self.zip, self.ia, self.revision)
        self.assertTrue(any('prohibida' in x for x in report['errores_integridad']))

    def test_etiqueta_invalida_rechazada(self):
        rows = self.rows()
        rows[0]['etiqueta_e0_e1_e2'] = 'SANO'
        self.replace(rows)
        report, _ = auditar(self.zip, self.ia, self.revision)
        self.assertTrue(report['errores_integridad'])

    def test_sin_revisor_humano_no_se_acepta(self):
        rows = self.rows()
        rows[1].update({'estado_revision': 'revisada_sin_etiqueta',
                        'observaciones_revisor': 'No se puede comprobar su cobertura.'})
        self.replace(rows)
        report, _ = auditar(self.zip, self.ia, self.revision)
        self.assertTrue(any('revisor humano' in s for s in report['errores_integridad']))

    def test_fecha_sin_zona_horaria_rechazada(self):
        rows = self.rows()
        rows[1].update({'estado_revision': 'no_evaluable', 'revisor_id': 'operador_1',
                        'fecha_revision_iso': '2026-11-05T10:10:10',
                        'observaciones_revisor': 'Vista física no verificable'})
        self.replace(rows)
        report, _ = auditar(self.zip, self.ia, self.revision)
        self.assertTrue(report['errores_integridad'])

    def test_exclusion_documentada_sin_etiqueta_es_admitida(self):
        rows = self.rows()
        rows[1].update({'estado_revision': 'no_evaluable', 'revisor_id': 'operador_1',
                        'fecha_revision_iso': '2026-11-05T10:10:10-05:00',
                        'observaciones_revisor': 'Vista lateral insuficiente'})
        self.replace(rows)
        report, _ = auditar(self.zip, self.ia, self.revision)
        self.assertFalse(report['errores_integridad'])
        self.assertEqual(report['revision']['tomate']['no_evaluables'], 1)

    def test_revisor_chatgpt_no_acredita_revision_humana(self):
        rows = self.rows()
        rows[1].update({'estado_revision': 'no_evaluable', 'revisor_id': 'ChatGPT',
                        'fecha_revision_iso': '2026-11-05T10:10:10-05:00',
                        'observaciones_revisor': 'Vista lateral insuficiente'})
        self.replace(rows)
        report, _ = auditar(self.zip, self.ia, self.revision)
        self.assertTrue(report['errores_integridad'])

    def test_mango_ataulfo_no_acredita_kent(self):
        rows = self.rows()
        rows[0].update({'estado_revision': 'etiquetada', 'etiqueta_e0_e1_e2': 'E0',
                        'rubrica_version': 'kent-ext-v0.5', 'revisor_id': 'operador_1',
                        'fecha_revision_iso': '2026-11-05T10:10:10-05:00',
                        'justificacion_rubrica': 'Observación independiente bajo rúbrica.',
                        'referencia_soporte_pieza_sesion': 'registro-privado-001',
                        'referencia_soporte_etiqueta': 'revision-privada-001'})
        self.replace(rows)
        report, _ = auditar(self.zip, self.ia, self.revision)
        self.assertTrue(any('Ataulfo' in x for x in report['errores_integridad']))

    def test_tomate_etiqueta_documental_no_habilita_entrenar(self):
        rows = self.rows()
        rows[1].update({'estado_revision': 'etiquetada', 'etiqueta_e0_e1_e2': 'E1',
                        'rubrica_version': 'tomato-ext-v0.2', 'revisor_id': 'operador_1',
                        'fecha_revision_iso': '2026-11-05T10:10:10-05:00',
                        'justificacion_rubrica': 'Observación independiente bajo rúbrica.',
                        'referencia_soporte_pieza_sesion': 'registro-privado-001',
                        'referencia_soporte_etiqueta': 'revision-privada-001'})
        self.replace(rows)
        report, _ = auditar(self.zip, self.ia, self.revision)
        self.assertFalse(report['errores_integridad'])
        self.assertEqual(report['revision']['tomate']['etiquetas_declaradas_sin_acreditacion_independiente']['E1'], 1)
        self.assertEqual(report['revision']['tomate']['etiquetas_acreditadas'], 0)
        self.assertFalse(report['AG034_cierre_total_acreditado'])

    def test_revision_ia_no_puede_contener_etiquetas_acreditadas(self):
        self.source_rows[0]['etiqueta_E0_E1_E2_acreditada'] = 'E0'
        write_csv(self.ia, self.source_rows)
        with self.assertRaises(ReviewError):
            generar_plantilla(self.zip, self.ia)

    def test_inventario_ia_no_coincidente_rechazado(self):
        self.source_rows[0]['sha256'] = '0' * 64
        write_csv(self.ia, self.source_rows)
        with self.assertRaises(ReviewError):
            generar_plantilla(self.zip, self.ia)

    def test_no_sobrescribe_plantilla_cli(self):
        path = self.base / 'form.csv'
        self.assertEqual(main(['plantilla', '--zip', str(self.zip), '--revision-ia', str(self.ia), '--salida', str(path)]), 0)
        original = path.read_bytes()
        self.assertEqual(main(['plantilla', '--zip', str(self.zip), '--revision-ia', str(self.ia), '--salida', str(path)]), 2)
        self.assertEqual(path.read_bytes(), original)

    def test_auditar_cli_genera_informe_y_estado(self):
        out = self.base / 'informe'
        self.assertEqual(main(['auditar', '--zip', str(self.zip), '--revision-ia', str(self.ia),
                               '--csv', str(self.revision), '--salida', str(out)]), 0)
        r = json.loads((out / 'AG034_revision_calidad_auditoria.json').read_text(encoding='utf-8'))
        self.assertFalse(r['AG034_cierre_total_acreditado'])
        self.assertIn('AG-034', (out / 'AG034_informe_revision_calidad.md').read_text(encoding='utf-8'))

    def test_verificar_reproduce_salida_y_hashes(self):
        out = self.base / 'auditado'
        self.assertEqual(main(['auditar', '--zip', str(self.zip), '--revision-ia', str(self.ia),
                               '--csv', str(self.revision), '--salida', str(out)]), 0)
        result = verificar(self.zip, self.ia, self.revision, out)
        self.assertEqual(result['estado'], 'integridad_revision_verificada')
        self.assertEqual(result['archivos_resultados'], 3)

    def test_verificar_detecta_alteracion_del_informe(self):
        out = self.base / 'auditado'
        self.assertEqual(main(['auditar', '--zip', str(self.zip), '--revision-ia', str(self.ia),
                               '--csv', str(self.revision), '--salida', str(out)]), 0)
        report = out / 'AG034_informe_revision_calidad.md'
        report.write_text(report.read_text(encoding='utf-8') + 'MODIFICADO', encoding='utf-8')
        with self.assertRaises(ReviewError):
            verificar(self.zip, self.ia, self.revision, out)

    def test_verificar_detecta_alteracion_del_csv_revision(self):
        out = self.base / 'auditado'
        self.assertEqual(main(['auditar', '--zip', str(self.zip), '--revision-ia', str(self.ia),
                               '--csv', str(self.revision), '--salida', str(out)]), 0)
        rows = self.rows()
        rows[0]['estado_revision'] = 'no_evaluable'
        rows[0]['revisor_id'] = 'operador1'
        rows[0]['fecha_revision_iso'] = '2026-11-05T11:00:00-05:00'
        rows[0]['observaciones_revisor'] = 'Imagen descartada por revisión'
        self.replace(rows)
        with self.assertRaises(ReviewError):
            verificar(self.zip, self.ia, self.revision, out)

    def test_no_modifica_dataset_y_csv_ia(self):
        before = (digest(self.zip.read_bytes()), digest(self.ia.read_bytes()))
        generar_plantilla(self.zip, self.ia)
        auditar(self.zip, self.ia, self.revision)
        after = (digest(self.zip.read_bytes()), digest(self.ia.read_bytes()))
        self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main()
