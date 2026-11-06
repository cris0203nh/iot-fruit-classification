# AGROP-42 — Incremento 02: baseline explicable de reglas técnicas

## Alcance real

Esta entrega implementa **reglas deterministas de preparación para revisión humana** sobre los
**resultados JSON ya procesados** por AGROP-40 (mango Kent) y AGROP-41 (tomate).

**No** clasifica E0/E1/E2, no predice enfermedades o defectos, no sustituye
la rúbrica ni la validación por un evaluador, **no** entrena ningún modelo,
**no** calcula accuracy, precision, recall o F1 y **no** compara todavía dos métodos.

El baseline técnico no puede presentarse como rendimiento de un algoritmo de
clasificación de frutas. Sirve para instrumentar un flujo de decisión reproducible
y registrar latencia **solo de reglas sobre JSON en memoria**, que no incluye
captura, lectura de fotografías, máscaras ni ejecución del pipeline de visión.

## Reglas y precedencia

| Regla | Condición | Decisión técnica |
|---|---|---|
| R01 | Producto declarado no admitido por pipeline | `fuera_de_alcance` |
| R03 | Reporte sin registros de imagen | `no_evaluable` |
| R04 | Cualquier imagen exige recaptura explícita | `recaptura_requerida` |
| R02 | Captura general `no_evaluable` | `no_evaluable` |
| R05 | Captura general `pendiente_revision` | `revision_de_captura_pendiente` |
| R06 | Reporte evaluable con imágenes no evaluables | `revision_de_captura_pendiente` |
| R07 | Propuesta incluye múltiples regiones ambiguas | `revision_de_segmentacion` |
| R08 | Máscara ausente o no seleccionada provisionalmente | `revision_de_segmentacion` |
| R09 | Captura y máscaras provisionalmente listas | `apta_para_revision_externa` |

Las reglas anteriores son identificadores **internos del baseline AGROP-42**;
no equivalen a R01–R10 de las rúbricas de mango/tomate. La última decisión significa
*lista para revisión externa humana*, nunca *fruta aprobada*.

## Comandos (raíz del repositorio en Windows)

### 1. Primero resolver importación de las fotos de Work

El error `No hay filas` indica que `carga_fotos.csv` era la plantilla vacía.
El ZIP de Work `AgroScan_AGROP42_Fotos_Reales.zip` trae su CSV con 19 filas y
las fotos en `entrada_fotos/mango_kent/` y `entrada_fotos/tomate/`.

```powershell
$zip = "$env:USERPROFILE\Downloads\AgroScan_AGROP42_Fotos_Reales.zip"
$destino = '.\vision\experiments\AGROP42'
Expand-Archive -LiteralPath $zip -DestinationPath $destino -Force
(Import-Csv "$destino\carga_fotos.csv").Count
```

La cuenta debe ser 19. Ajustar `$zip` si el archivo se encuentra en otro lugar.
Usar un directorio nuevo de salida para no pisar resultados previos:

```powershell
.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.preparar_dataset `
  --csv vision/experiments/AGROP42/carga_fotos.csv `
  --input-dir vision/experiments/AGROP42/entrada_fotos `
  --output-dir vision/experiments/AGROP42/dataset_work_v1

.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.auditar `
  --manifests-dir vision/experiments/AGROP42/dataset_work_v1/manifests `
  --annotations vision/experiments/AGROP42/dataset_work_v1/annotations_to_review.json `
  --output vision/experiments/AGROP42/auditoria_work_v1.json
```

El informe de auditoría **debe continuar bloqueado** hasta contar con piezas/sesiones
y etiquetas revisadas. El auditor puede sumar imágenes locales de SQLite:
se deben observar también los subtotales por fuente, no inferir que todo procede del ZIP.

### 2. Ejecutar el baseline de reglas sobre informes procesados

```powershell
.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.baseline_reglas `
  --reports-dir vision/experiments `
  --audit vision/experiments/AGROP42/auditoria_work_v1.json `
  --output vision/experiments/AGROP42/baseline_reglas_v1.json `
  --repeats 30
```

`--reports-dir` debe contener resultados JSON previos de los pipelines
(`resultado_mango_revision.json`, `resultado_tomate_*.json`, etc.).
**Los manifiestos exportados por el importador no son resultados del pipeline**:
no cuentan en el baseline hasta ejecutar mango/tomate sobre cada imagen.

Consultar:

```powershell
$r = Get-Content vision/experiments/AGROP42/baseline_reglas_v1.json -Raw -Encoding UTF8 | ConvertFrom-Json
$r.status
$r.evaluated_pipeline_reports
$r.decisions_by_product | ConvertTo-Json -Depth 6
$r.timing | ConvertTo-Json -Depth 5
$r.comparison | ConvertTo-Json -Depth 5
```

### 3. Tests

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s vision/tests -p 'test_*.py' -q
```

Son 25 pruebas nuevas en este incremento (un total **esperado** de 108
si los 83 tests previos están presentes; validar el total en Windows).

## Trazabilidad y límites

- No toca los módulos de AGROP-39, AGROP-40 ni AGROP-41.
- No se cuentan múltiples reportes de una misma fotografía como muestras independientes.
- El baseline no requiere un detector entrenado, pero tampoco permite comparación de
  exactitud supervisada con un modelo ligero sin etiquetas verificadas y splits.
- La latencia de estas reglas es de procesamiento de diccionarios JSON, medida en la máquina local.
  La comparación futura con un modelo tendrá que medir ambos bajo condiciones comparables.
- Mantener los datos del ZIP, CSV, reportes y los JSON de auditoría en `vision/experiments/`,
  excluidos por `.gitignore`.
