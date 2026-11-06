"""Contratos de AG-034 / Incremento 11 (muestras sintéticas SOLO de test)."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from vision.evaluation.agrop42.consolidar_ag034 import EvidenceError, generar, validar, verificar


def digest(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def csv_bytes(rows: list[dict]) -> bytes:
    f = io.StringIO(newline='')
    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return f.getvalue().encode('utf-8')


class ConsolidacionIncremento11Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.evidence = self.root / 'evidencias'
        self.zip = self.root / 'datos.zip'
        self.out = self.root / 'salida'
        self.rgb, self.rev, self.bm, self.perfil, self.rgb_report = [], [], {}, {}, {}
        self.images = {}
        for product, plural in (('mango', 'mangos'), ('tomate', 'tomates')):
            for piece in (1, 2):
                pid = f'{product.upper()}_{piece:02d}'
                for view in (1, 2, 3):
                    path = f'{plural}/{pid}/vista_{view:02d}.jpg'
                    payload = f'foto_sintetica_test_{path}'.encode('utf-8')
                    self.images[path] = payload
                    sha = digest(payload)
                    state = 'unavailable' if (product, piece, view) == ('mango', 1, 1) else 'pending_operator_selection'
                    self.rgb.append({'producto': product, 'id_ejemplar_fuente': pid, 'vista': str(view), 'sha256': sha,
                                     'mascara_estado': state, 'operador_confirmo_region': 'no',
                                     'etiqueta_e0_e1_e2': ''})
                    self.rev.append({'producto': product, 'id_ejemplar_fuente': pid, 'vista': str(view), 'sha256': sha,
                                     'archivo_origen': path,
                                     'revision_visual_mascara_IA': 'sin_mascara' if state == 'unavailable' else 'compatible_visual_provisional',
                                     'etiqueta_E0_E1_E2_acreditada': '',
                                     'aprobacion_operador_o_experto': 'pendiente',
                                     'identidad_fisica_verificada': 'no',
                                     'sesion_captura_AgroScan_verificada': 'no',
                                     'utilizable_para_entrenamiento_comercial': 'no'})
        with ZipFile(self.zip, 'w') as z:
            trace = []
            for path, payload in self.images.items():
                z.writestr(path, payload)
                parts = path.split('/')
                trace.append({'archivo': path, 'id_ejemplar': parts[1], 'vista': str(int(parts[2][-6:-4])),
                              'sha256': digest(payload)})
            z.writestr('trazabilidad.csv', csv_bytes(trace))
        self.rgb_report = {
            'fotografias_procesadas': 12, 'identificadores_de_fuente': 4,
            'entrenamiento_autorizado': False, 'etiquetas_e0_e1_e2_verificadas': 0,
            'regiones_confirmadas_por_operador': 0, 'modelo_entrenado': False,
            'conteo_por_producto': {
                'mango': {'fotografias': 6, 'ejemplares_declarados_por_fuente': 2, 'fotos_con_mascara_candidata': 5},
                'tomate': {'fotografias': 6, 'ejemplares_declarados_por_fuente': 2, 'fotos_con_mascara_candidata': 6},
            },
        }
        confusion = {'mango': {'mango': 3, 'tomate': 0}, 'tomate': {'mango': 0, 'tomate': 3}}
        metric = {'n_vistas': 6, 'accuracy_vistas': 1.0, 'matriz_confusion_fuente': confusion}
        predicted = [{
            'archivo': row['archivo_origen'], 'id_ejemplar': row['id_ejemplar_fuente'],
            'producto_fuente': row['producto'], 'reglas': row['producto'], 'modelo_ligero': row['producto'],
        } for row in self.rev if row['id_ejemplar_fuente'].endswith('_01')]
        self.bm = {'AG034_cierre_total_acreditado': False,
                   'totales': {'vistas': 12, 'grupos_fuente': 4, 'vistas_train': 6, 'vistas_val': 0, 'vistas_test': 6},
                   'predicciones_test': predicted,
                   'evaluacion_prueba_comun': {'reglas': metric, 'modelo_ligero': metric}}
        method = lambda med, dur, model: {
            'metricas_test': metric, 'inferencia_sin_extraccion': {'mediana_ms': med},
            'pipeline_completo_en_equipo_local': {'mediana_ms': dur, 'p95_ms': dur * 1.2},
            'modelo_json_bytes': model, 'tracemalloc_pico_mib_en_test': 0.5,
        }
        self.perfil = {
            'zip_sha256': digest(self.zip.read_bytes()),
            'dataset': {'vistas': 12, 'grupos_fuente_declarados': 4,
                        'particion_vistas': {'entrenamiento': 6, 'validacion': 0, 'prueba': 6},
                        'independencia_fisica_de_piezas_acreditada': False},
            'entorno': {'sistema': 'Equipo de pruebas', 'python': '3.13'},
            'enfoques': {'reglas': method(.0001, 5, 94), 'modelo_ligero': method(.001, 4, 778)},
            'decision': {'cierre_total_AG034_acreditado': False, 'hardware_objetivo_validado': False,
                         'clasificacion_e0_e1_e2_evaluada': False, 'despliegue_autorizado': False},
        }
        self.write_sources()

    def write_sources(self):
        paths = {
            'incremento08/resultados_por_vista.csv': csv_bytes(self.rgb),
            'incremento08/informe_tecnico.json': json.dumps(self.rgb_report).encode(),
            'incremento09/AG034_revision_visual_90_vistas_IA.csv': csv_bytes(self.rev),
            'incremento09/AG034_benchmark_auxiliar.json': json.dumps(self.bm).encode(),
            'incremento10/AG034_perfil_recursos.json': json.dumps(self.perfil).encode(),
        }
        for rel, blob in paths.items():
            p = self.evidence / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(blob)

    def test_consolida_y_verifica_copias_sin_modificar_fuentes(self):
        before = {str(p.relative_to(self.evidence)): digest(p.read_bytes()) for p in self.evidence.rglob('*') if p.is_file()}
        result = generar(self.evidence, self.zip, self.out)
        self.assertEqual(result['dataset']['fotografias'], 12)
        self.assertEqual(result['segmentacion']['mascaras_candidatas'], 11)
        self.assertEqual(result['benchmark']['test_grupos_fuente'], 2)
        self.assertFalse(result['cierre']['AG034_cierre_total_acreditado'])
        self.assertEqual(verificar(self.out, self.zip)['archivos_verificados'], 8)
        after = {str(p.relative_to(self.evidence)): digest(p.read_bytes()) for p in self.evidence.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_rechaza_duplicado_identificador_y_vista(self):
        self.rgb.append(dict(self.rgb[0]))
        self.write_sources()
        with self.assertRaisesRegex(EvidenceError, 'duplicado'):
            validar(self.evidence, self.zip)

    def test_rechaza_sha_alterado_en_revision(self):
        self.rev[0]['sha256'] = '0' * 64
        self.write_sources()
        with self.assertRaisesRegex(EvidenceError, 'SHA'):
            validar(self.evidence, self.zip)

    def test_rechaza_zip_distinto_a_perfil(self):
        self.perfil['zip_sha256'] = 'b' * 64
        self.write_sources()
        with self.assertRaisesRegex(EvidenceError, 'ZIP diferente'):
            validar(self.evidence, self.zip)

    def test_rechaza_revision_con_etiqueta_e0_sin_aprobacion(self):
        self.rev[0]['etiqueta_E0_E1_E2_acreditada'] = 'E0'
        self.write_sources()
        with self.assertRaisesRegex(EvidenceError, 'acreditación humana'):
            validar(self.evidence, self.zip)

    def test_rechaza_rol_operador_aprobado_sin_soporte(self):
        self.rev[0]['aprobacion_operador_o_experto'] = 'aprobado'
        self.write_sources()
        with self.assertRaisesRegex(EvidenceError, 'acreditación humana'):
            validar(self.evidence, self.zip)

    def test_rechaza_mascara_confirmada_por_csv(self):
        self.rgb[1]['operador_confirmo_region'] = 'si'
        self.write_sources()
        with self.assertRaisesRegex(EvidenceError, 'acreditación humana'):
            validar(self.evidence, self.zip)

    def test_rechaza_mascara_ficticia_sobre_ausencia_en_08(self):
        self.rev[0]['revision_visual_mascara_IA'] = 'compatible_visual_provisional'
        self.write_sources()
        with self.assertRaisesRegex(EvidenceError, 'no existe'):
            validar(self.evidence, self.zip)

    def test_rechaza_matriz_confusion_falsa(self):
        self.bm['evaluacion_prueba_comun']['reglas']['matriz_confusion_fuente']['mango']['mango'] = 2
        self.write_sources()
        with self.assertRaises(EvidenceError):
            validar(self.evidence, self.zip)

    def test_rechaza_prediccion_de_fruta_ajena(self):
        self.bm['predicciones_test'][0]['id_ejemplar'] = 'MANGO_99'
        self.write_sources()
        with self.assertRaisesRegex(EvidenceError, 'ID no coincidente'):
            validar(self.evidence, self.zip)

    def test_rechaza_predicciones_con_fuga_de_vistas(self):
        self.bm['predicciones_test'][0]['archivo'] = 'mangos/MANGO_02/vista_01.jpg'
        self.bm['predicciones_test'][0]['id_ejemplar'] = 'MANGO_02'
        self.write_sources()
        with self.assertRaises(EvidenceError):
            validar(self.evidence, self.zip)

    def test_rechaza_particiones_inconsistentes_09_10(self):
        self.perfil['dataset']['particion_vistas']['prueba'] = 9
        self.write_sources()
        with self.assertRaisesRegex(EvidenceError, 'Particiones'):
            validar(self.evidence, self.zip)

    def test_rechaza_hardware_incorrectamente_acreditado(self):
        self.perfil['decision']['hardware_objetivo_validado'] = True
        self.write_sources()
        with self.assertRaisesRegex(EvidenceError, 'acreditación no sustentada'):
            validar(self.evidence, self.zip)

    def test_no_sobrescribe_salida(self):
        generar(self.evidence, self.zip, self.out)
        with self.assertRaisesRegex(EvidenceError, 'existe'):
            generar(self.evidence, self.zip, self.out)

    def test_no_deja_salida_si_csv_no_coincide(self):
        self.rgb[0]['sha256'] = '0' * 64
        self.write_sources()
        with self.assertRaises(EvidenceError):
            generar(self.evidence, self.zip, self.out)
        self.assertFalse(self.out.exists())

    def test_verificacion_detecta_alteracion_de_informe(self):
        generar(self.evidence, self.zip, self.out)
        with (self.out / 'AG034_informe_para_Jira.md').open('a', encoding='utf-8') as f:
            f.write('cambiado')
        with self.assertRaisesRegex(EvidenceError, 'alterada'):
            verificar(self.out, self.zip)

    def test_verificacion_detecta_cambio_en_evidencia_copiada(self):
        generar(self.evidence, self.zip, self.out)
        p = self.out / 'fuentes' / 'incremento08' / 'informe_tecnico.json'
        p.write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(EvidenceError, 'alterada'):
            verificar(self.out, self.zip)

    def test_verificacion_detecta_archivo_inesperado(self):
        generar(self.evidence, self.zip, self.out)
        (self.out / 'archivo_sorpresa.txt').write_text('hola', encoding='utf-8')
        with self.assertRaisesRegex(EvidenceError, 'agregados'):
            verificar(self.out, self.zip)

    def test_rechaza_zip_con_archivo_fotografico_alterado(self):
        with ZipFile(self.zip, 'a') as z:
            z.writestr('mangos/MANGO_01/extra.jpg', b'extra')
        self.perfil['zip_sha256'] = digest(self.zip.read_bytes())
        self.write_sources()
        with self.assertRaisesRegex(EvidenceError, 'sin inventariar'):
            validar(self.evidence, self.zip)

    def test_texto_jira_no_presenta_entrenamiento_autorizado(self):
        generar(self.evidence, self.zip, self.out)
        t = (self.out / 'AG034_informe_para_Jira.md').read_text(encoding='utf-8')
        self.assertIn('cierre parcial', t.lower())
        self.assertIn('no acreditada', t)
        self.assertIn('reglas clásicas', t)


if __name__ == '__main__':
    unittest.main()
