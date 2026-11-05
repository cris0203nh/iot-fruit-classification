# AGROP-40 [AG-032] — Pipeline experimental para mango Kent

**Referencia documental:** AGROP-13, `kent-ext-v0.5` (29/10/2026), de Fernando Ramírez. El desarrollo se limita a **mango Kent declarado**, sin reconocimiento automático de variedad.

## Estado y alcance

Este incremento implementa un **baseline técnico de procesamiento RGB y contrato de salida**. **No** existe aún un clasificador entrenado/validado de defectos; **no** se asigna automáticamente E0/E1/E2 y **no** se determina madurez interna, Brix, firmeza, sabor, inocuidad ni categoría comercial. La evaluación automática de R03–R06 queda `no_determinable` hasta disponer de anotaciones confiables y experimento de validación.

Se mantiene separado el calibre por peso verificado (R02) del estado visual. Los descriptores RGB y razón geométrica solo se obtienen de una región rectangular de interés **confirmada manualmente**; no corresponden a segmentación validada de la cáscara. No se convierten píxeles a cm² ni a milímetros.

### Criterios de rúbrica

| Criterio | Salida del incremento |
|---|---|
| R01 Identidad y cobertura | Estado `evaluable`, `no_evaluable`, `pendiente_revision` o `no_reconocido` con razones |
| R02 Peso y calibre | A/B/C únicamente con peso, calibración, estabilidad e incertidumbre verificados; independiente del resultado visual |
| R03 Integridad superficial | `no_determinable` sin modelo/anotación validada |
| R04 Deterioro visible | `no_determinable` sin modelo/anotación validada |
| R05 Defectos de cáscara | `no_determinable` sin modelo/anotación validada |
| R06 Limpieza e indicios de plagas | `no_determinable` sin modelo/anotación validada |
| R07 Forma y color | Medianas RGB y relación alto/ancho de ROI verificada, **descriptivas** y sin clasificación comercial |
| R08 No observables | Se excluyen expresamente firmeza, Brix, sabor y condición interna |

`evaluable` indica solo que la **captura** ha sido declarada suficiente para revisión. No significa que una fruta no tenga defectos ni que exista una predicción. E0, E1 y E2 requieren revisión humana o un modelo validado.

**La validación de cobertura, enfoque, iluminación y oclusiones se suministra en el manifiesto como declaración explícita del operador; el software NO la comprueba automáticamente.** Parámetro provisional técnico de dimensión mínima: 128 px por lado; no es una especificación agronómica.

## Ejecutar en Windows desde la raíz del repositorio

1. Instalar Pillow en el entorno virtual que utilizarás para visión (ejemplo: `backend/.venv/Scripts/python.exe -m pip install -r vision/requirements.txt`). También se puede usar un entorno dedicado.
2. Copiar `vision/examples/mango_kent_manifest.example.json` a un archivo local, por ejemplo `vision/experiments/mi_mango.json` (no subir datos de prueba al repositorio).
3. Sustituir los identificadores por los reales y la ruta de la fotografía. Las rutas relativas se interpretan respecto al directorio del manifiesto. Si no has verificado calidad, cobertura o ROI, deja los campos `null` o `false` sin inventar verificaciones.
4. Ejecutar:

```powershell
.\backend\.venv\Scripts\python.exe -m vision.src.mango_pipeline --manifest vision/experiments/mi_mango.json --output vision/experiments/resultado_mango.json
```

Para introducir una ROI revisada, `roi_xywh` recibe `[x, y, ancho, alto]` en píxeles, con origen superior izquierdo. Coloca `roi_verified: true` únicamente si verificaste que la región corresponde a la superficie que estás describiendo. En imágenes de varias frutas, NO asignar una sola región a una pieza sin identificarla de forma inequívoca.

**No subir el manifiesto local ni las fotografías reales por defecto**: pueden contener rutas y datos de trabajo. `vision/experiments/` debe excluirse de los commits de este incremento salvo que se revisen explícitamente los archivos a publicar.

## Pruebas reproducibles

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s vision/tests -p "test_*.py" -v
```

Las pruebas crean temporalmente una imagen uniforme de píxeles para verificar contratos y reglas. **No constituyen un experimento de exactitud de visión sobre frutas reales.**

## Dependencia AGROP-39 y límites

El PR #41 creó el particionador `backend/dataset/particionar_datos.py` y reportó solo **un** grupo independiente verificable, por lo que no generó un conjunto completo de entrenamiento/validación/prueba. Este incremento de AGROP-40 no modifica el particionador ni afirma que se haya entrenado un modelo. La evaluación de exactitud queda condicionada a datos de mango Kent etiquetados, revisados y correctamente separados por pieza y sesión.

## Próximo incremento

Integrar anotaciones verificadas de R03–R06 y un experimento cuantitativo con imágenes de mango reales, revisión independiente y sin filtración entre particiones. La versión `kent-ext-v1.0` de la rúbrica **no está aprobada** según AGROP-13.
