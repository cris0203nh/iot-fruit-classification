"""Pruebas sin acceso a hardware ni imágenes para el filtro AGROP-42."""
import csv
import tempfile
import unittest
from pathlib import Path

from vision.evaluation.agrop42.auditar_revisiones import COLUMNAS, auditar_csv, _grupos_independientes


class AuditoriaAGROP42Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'revisiones.csv'

    @staticmethod
    def fila(i, producto='mango', etiqueta='', *, pieza=None, sesion=None, revisada=False):
        fila = dict.fromkeys(COLUMNAS, '')
        fila.update({
            'registro_id':f'R-{i}', 'producto':producto,
            'sha256':f'{i:064x}', 'archivo': f'images/{i}.jpg',
            'estado_revision':'revisada', 'etiqueta_visual':etiqueta,
        })
        if revisada:
            fila.update({
                'revisor_id': 'operador-test', 'revisado_en':'2026-11-05',
                'rubrica_version':'ejemplo-test', 'calidad_confirmada':'true',
                'cobertura_confirmada':'true','pieza_confirmada':'true',
                'sesion_confirmada':'true', 'lote_id':'L1',
                'pieza_id':pieza or f'P{i}', 'sesion_id':sesion or f'S{i}',
                'dispositivo_id':'D1', 'evidencia_pieza':'acta-P',
                'evidencia_sesion':'acta-S', 'justificacion_etiqueta':'anotación test'
            })
        return fila

    def guardar(self, filas):
        with self.path.open('w',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=sorted(COLUMNAS))
            writer.writeheader();writer.writerows(filas)

    def test_solo_notas_aprobadas_no_habilita_entrenamiento(self):
        self.guardar([self.fila(i,etiqueta='') for i in range(1,20)])
        r=auditar_csv(self.path)
        self.assertEqual(r['estado_global'],'bloqueado_por_datos_insuficientes')
        self.assertEqual(r['productos']['mango']['etiquetas_elegibles'],0)
        self.assertIsNone(r['metricas_estimadas'])

    def test_clase_sin_trazabilidad_no_es_elegible(self):
        self.guardar([self.fila(1,etiqueta='E0')])
        self.assertEqual(auditar_csv(self.path)['productos']['mango']['etiquetas_elegibles'],0)

    def test_grupos_independientes_requieren_piezas_y_sesiones_distintas(self):
        filas=[self.fila(1,'mango','E0',pieza='P1',sesion='S1',revisada=True),
               self.fila(2,'mango','E1',pieza='P2',sesion='S1',revisada=True),
               self.fila(3,'mango','E1',pieza='P2',sesion='S2',revisada=True)]
        self.assertEqual(_grupos_independientes(filas),1)

    def test_tres_grupos_dos_clases_habilitan_solo_diseno(self):
        filas=[self.fila(1,'mango','E0',revisada=True),
               self.fila(2,'mango','E1',revisada=True),
               self.fila(3,'mango','E0',revisada=True)]
        self.guardar(filas)
        r=auditar_csv(self.path)
        self.assertEqual(r['productos']['mango']['estado'],'apto_para_diseno_experimental')
        self.assertEqual(r['estado_global'],'bloqueado_por_datos_insuficientes')
        self.assertFalse(r['evaluacion_ejecutada'])

    def test_informacion_tomate_no_suple_mango(self):
        self.guardar([self.fila(i,'tomate','E0' if i%2 else 'E1',revisada=True) for i in range(1,4)])
        self.assertEqual(auditar_csv(self.path)['productos']['mango']['fotografias'],0)

    def test_sha_repetido_produce_error_y_bloquea(self):
        a,b=self.fila(1),self.fila(2)
        b['sha256']=a['sha256']
        self.guardar([a,b])
        r=auditar_csv(self.path)
        self.assertTrue(r['errores_integridad'])

    def test_ruta_insegura_produce_error(self):
        a=self.fila(1);a['archivo']='../secreto.txt'
        self.guardar([a])
        self.assertTrue(auditar_csv(self.path)['errores_integridad'])

    def test_fecha_invalida_no_acredita_revision(self):
        a=self.fila(1,'mango','E0',revisada=True);a['revisado_en']='ayer'
        self.guardar([a])
        self.assertEqual(auditar_csv(self.path)['productos']['mango']['etiquetas_elegibles'],0)

    def test_etiqueta_no_evaluable_no_entrena(self):
        a=self.fila(1,'mango','E1',revisada=True);a['estado_revision']='no_evaluable'
        self.guardar([a])
        self.assertEqual(auditar_csv(self.path)['productos']['mango']['etiquetas_elegibles'],0)

    def test_esquema_incompleto_se_rechaza(self):
        self.path.write_text('registro_id,producto\nR1,mango\n',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Columnas obligatorias faltantes'):
            auditar_csv(self.path)


if __name__ == '__main__':
    unittest.main()
