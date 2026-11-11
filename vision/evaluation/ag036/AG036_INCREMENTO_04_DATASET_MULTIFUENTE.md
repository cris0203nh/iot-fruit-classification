# AgroScan — AG-036 / AGROP-44 — Incremento 04: ingesta multifuente y detección exploratoria

## Situación documentada

Se recibieron **82 imágenes JPEG** en el archivo `AgroScan_Imagenes_Revisadas.zip`:

| Carpeta declarada | Imágenes | Grupos de carpeta | Identidad acreditada |
|---|---:|---:|---|
| Capturas proyecto: mango, variedad pendiente | 8 | 3 | Sin confirmar |
| Capturas proyecto: tomate, tipo pendiente | 14 | 2 | Sin confirmar |
| Externo: mango Kent COFiLAB, dos vistas | 30 | 15 | Fuente y variedad sin corroboración independiente |
| Externo: tomate Cherry Red Fruits-360 | 30 | 1 | Secuencia de un grupo, no 30 piezas independientes |
| **Total** | **82** | **21** | **0 piezas acreditadas automáticamente** |

- Las 82 imágenes se decodificaron correctamente y presentan 82 hashes SHA256 distintos; esto **no** descarta fotos similares de la misma fruta.
- Once imágenes del grupo externo de tomate tienen alguna dimensión menor a 224 px; se mantienen y se señalan con advertencia para evaluar su utilidad.
- La carpeta `Candidato_T02` contiene once imágenes asociadas a seis códigos de evaluación `E-*` distintos. El nombre de carpeta **no acredita** que todas pertenezcan a una sola pieza.
- Las carpetas externas declaran un origen, pero los ficheros no contienen manifiesto original, autorización individual ni actas humanas. La licencia debe comprobarse con el origen exacto. La licencia general de Fruits-360 no reemplaza esa verificación.
- La versión del clasificador YOLOE de AgroScan detecta/segmenta mango y tomate; **no produce E0/E1/E2**. No se debe entrenar un clasificador supervisado de condición externa usando etiquetas deducidas de nombres, colores o confianza de detección.

## Archivos nuevos

1. `ingestar_dataset_multifuente.py`: extrae de forma controlada JPG/PNG; comprueba formatos, dimensiones, rutas seguras, tamaños y SHA256; conserva las 82 imágenes; crea `inventario_multifuente.csv`, `grupos_candidatos.csv`, `universo_AG036_borrador.csv`, `resumen_multifuente.json` y un documento LEEME. **No completa** lote, pieza, sesión, variedad ni rúbrica sin evidencia.
2. `evaluar_detector_multifuente.py`: ejecuta opcionalmente YOLOE para **las 82 fotografías**, guardando por imagen predicciones de detección de mango/tomate, confianza, existencia de polígono de segmentación, conteos y advertencias. NO genera etiquetas E0/E1/E2 ni estimaciones de accuracy; para eso hacen falta referencias humanas independientes.
3. `vision/tests/test_ag036_ingesta_multifuente.py` y `test_ag036_detector_multifuente.py`: 25 pruebas sintéticas que cubren procedencia, integridad, hashes, seguridad del ZIP, grupos no confirmados y lógica del informe de detección. Las pruebas de YOLOE usan un simulador del detector y **no equivalen** a 82 inferencias reales.

## Comandos PowerShell desde la raíz del proyecto

**Primero:** comprobar el estado de Git. Si `main` avanzó, fusionarlo en la rama actual sin ejecutar `reset --hard` ni añadir archivos desconocidos.

```powershell
$py = '.\backend\.venv\Scripts\python.exe'
$zip = Join-Path $env:USERPROFILE 'Downloads\AgroScan_Imagenes_Revisadas.zip'
$trabajo = Join-Path $env:USERPROFILE 'Documents\AgroScan_AG036_Multifuente'

& $py -m vision.evaluation.ag036.ingestar_dataset_multifuente `
  --zip $zip `
  --salida-dir $trabajo

# Una muestra de cinco inferencias (rápida validación del flujo)
& $py -m vision.evaluation.ag036.evaluar_detector_multifuente `
  --inventario (Join-Path $trabajo 'inventario_multifuente.csv') `
  --raiz-imagenes (Join-Path $trabajo 'imagenes') `
  --salida-dir (Join-Path $env:USERPROFILE 'Documents\AgroScan_AG036_Deteccion_Muestra') `
  --limite 5

# Para analizar las 82 imágenes completas, usar salida diferente
& $py -m vision.evaluation.ag036.evaluar_detector_multifuente `
  --inventario (Join-Path $trabajo 'inventario_multifuente.csv') `
  --raiz-imagenes (Join-Path $trabajo 'imagenes') `
  --salida-dir (Join-Path $env:USERPROFILE 'Documents\AgroScan_AG036_Deteccion_82')
```

El valor `--limite 5` sirve únicamente para la prueba inicial. **Omitirlo** para utilizar todas las fotografías. La carpeta de salida no debe existir de antemano: así se evita sobrescribir evidencia.

Si en tu equipo ya extrajiste las imágenes, puedes emplear directamente el kit de inventario entregado con este incremento; no es necesario duplicar nuevamente las fotos. No ejecutar detección dos veces si la salida existente debe conservarse.

## Pruebas de regresión

```powershell
& $py -m unittest discover -s vision/tests -p 'test_ag036_*multifuente.py' -q
& $py -m unittest discover -s vision/tests -p 'test_ag036_*.py' -q
& $py -m unittest discover -s vision/tests -p 'test_*.py' -q
```

## Límites y siguiente paso experimental

- La doble revisión humana de AG-036 debe seleccionar **piezas** reales identificadas, no únicamente fotos ni nombres de carpeta. Las dos personas ven las mismas vistas de cada pieza, sin comunicarse las etiquetas. La aceptación final requiere respaldo documental y revisión de discrepancias.
- El `universo_AG036_borrador.csv` de este incremento está deliberadamente **incompleto**. No se debe ingresar directamente al auditor `auditar_etiquetado.py` ni rellenarlo en bloque suponiendo que un grupo sea una pieza.
- Para AG-034 (comparación supervisada E0/E1/E2), el programa exige suficientes **componentes independientes por clase y producto** y tres particiones sin fuga; tener 82 vistas no satisface ese requisito si son pocas piezas sin etiqueta.
- Para AG-035 visual, las métricas solo son calculables frente a una referencia humana adecuada y predicciones E0/E1/E2 de un modelo de calidad, **no** predicciones de detección de YOLOE.
- Nunca subir fotos privadas, actas de personas ni datasets externos sin comprobar licencias al repositorio público.
