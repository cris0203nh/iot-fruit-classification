"""Pruebas de integridad del contraste metodológico auxiliar AG-034."""
import csv
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from PIL import Image
from vision.evaluation.agrop42.benchmark_producto_ag034 import (
    FEATURES,choose_classical,fit_linear,get_features,linear_predict,
    metrics,rule_predict,run,split_groups,
)


class BenchProductoAG034Tests(unittest.TestCase):
    def _rows(self):
        return [
            {'producto': p, 'id_ejemplar': f'{p}_{i:02d}', 'y': int(p == 'tomate'), 'features': [float(i+j)]*len(FEATURES)}
            for p in ('mango','tomate') for i in range(1,16) for j in range(3)
        ]

    def test_particion_sin_fugas_por_identificador(self):
        rows=self._rows(); mapping=split_groups(rows)
        self.assertEqual(len(mapping),30)
        for p in ('mango','tomate'):
            self.assertEqual([v for key,v in mapping.items() if key[0] == p].count('entrenamiento'),9)
            self.assertEqual([v for key,v in mapping.items() if key[0] == p].count('validacion'),3)
            self.assertEqual([v for key,v in mapping.items() if key[0] == p].count('prueba'),3)
        self.assertEqual(mapping,split_groups(rows))

    def test_regla_se_entrena_solo_con_train(self):
        tr=[{'features':[x]*len(FEATURES),'y':y} for x,y in [(0,0),(.1,0),(.8,1),(1,1)]]
        rule=choose_classical(tr)
        self.assertEqual([rule_predict(rule,r['features']) for r in tr],[0,0,1,1])

    def test_modelo_ligero_sin_pickle(self):
        tr=[{'features':[x]*len(FEATURES),'y':y} for x,y in [(0,0),(.1,0),(.8,1),(1,1)]]
        model=fit_linear(tr)
        self.assertLess(linear_predict(model,[0]*len(FEATURES)),linear_predict(model,[1]*len(FEATURES)))
        json.dumps(model)

    def test_matriz_confusion_usando_mismo_test(self):
        tr=[{'features':[0]*len(FEATURES),'y':0},{'features':[1]*len(FEATURES),'y':1}]
        self.assertEqual(metrics(tr,lambda x:int(x[0]>.5))['accuracy_vistas'],1)

    def test_features_sin_ninguna_etiqueta_de_defecto(self):
        im=Image.new('RGB',(160,160),(250,250,250))
        for x in range(40,100):
            for y in range(30,100): im.putpixel((x,y),(240,25,20))
        f=get_features(im)
        self.assertEqual(len(f),len(FEATURES))
        self.assertTrue(all(isinstance(v,float) for v in f))

    def test_sha_alterado_se_rechaza(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'dataset.zip';im=Image.new('RGB',(200,200),(255,0,0));buff=io.BytesIO();im.save(buff,format='JPEG')
            with ZipFile(p,'w') as z:
                z.writestr('mangos/MANGO_01/vista_01.jpg',buff.getvalue())
                z.writestr('trazabilidad.csv','archivo,id_ejemplar,sha256\nmangos/MANGO_01/vista_01.jpg,MANGO_01,'+'0'*64+'\n')
            with self.assertRaisesRegex(ValueError,'SHA-256'):run(p,Path(temp)/'output.json')


if __name__=='__main__':unittest.main()
