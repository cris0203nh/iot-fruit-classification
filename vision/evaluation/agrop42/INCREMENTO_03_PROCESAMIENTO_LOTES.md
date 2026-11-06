# AGROP-42 — Incremento 03: procesamiento experimental por lotes

## Finalidad y límites

Procesa las fotografías originales incorporadas por `preparar_dataset.py` (01A), usando
**los módulos cromáticos de AGROP-40/41**: propuestas de regiones, máscaras y descriptores RGB.
No necesita inventar identidad de pieza, dispositivo, sesión, calidad o cobertura. **No es
una evaluación formal de las rúbricas** ni convierte esos descriptores en etiquetas E0/E1/E2.

Los manifiestos del ZIP de Work tienen `piece_id: null`, sesión ausente y calidad pendiente.
Por ello, **`tomato_pipeline.py` no debe ejecutarse como si hubiera identidad de pieza**:
se usa únicamente su adaptador existente `tomato_surface.py`. Mango usa los módulos
`surface_analysis.py` y `surface_masks.py`. El baseline 02 (`baseline_reglas.py`) sigue
recibiendo **solo informes formales de AGROP-40/41**; sus recuentos anteriores no se alteran.
Este incremento proporciona su propia decisión de **trazabilidad/revisión** para las 19 fotos.

### Integridad y tratamiento de imágenes

- Valida `inventory.json` de 01A, `visible_to_audit`, derechos declarados y SHA256 del archivo.
- Rechaza duplicados interproducto por SHA; dos registros con el mismo SHA y producto
  se procesan **una sola vez** y conservan la vinculación con todos sus registros.
- Bloquea rutas fuera de `images/`; no modifica originales, inventario ni base SQLite.
- Límite técnico: archivos PNG/JPEG hasta 30 MiB y resolución hasta 40 megapíxeles.
- Registra `source_id`, URL, licencia y variedad declarada. **Una declaración no prueba variedad Kent**.
- `results/*.json` describe píxeles cromáticos, no defectos, firmeza, madurez ni calidad comercial.
- `previews/*.png`: vistas de diagnóstico de hasta 960 px. La máscara de la miniatura se
  recalcula solamente **para visualizar**; los descriptores JSON se calculan sobre el original.

## Ejecución en Windows PowerShell (raíz del repositorio)

### 1. Pruebas

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s vision/tests -p "test_*.py" -q
```

El incremento añade **18 pruebas nuevas**. Partiendo de las 108 que ya ejecutaste,
se esperan **126/126**; la cuenta definitiva debe comprobarse en tu equipo.

### 2. Procesar las 19 imágenes del dataset importado

```powershell
.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.procesar_lotes `
  --dataset-dir vision/experiments/AGROP42/dataset_work_v1 `
  --output-dir vision/experiments/AGROP42/procesamiento_lotes_v1 `
  --repeats 3
```

**Requisitos:** `dataset_work_v1` existe y contiene `inventory.json` e `images/`. La
carpeta `procesamiento_lotes_v1` **no debe existir**. Para volver a ejecutar, usa
`procesamiento_lotes_v2` como nuevo destino. El programa no sobrescribe resultados.

El proceso genera `summary.json`, un informe por imagen SHA única en `results/` y
hasta dos diagnósticos PNG por imagen en `previews/`.

Para ejecutar sin generar PNG (más rápido):

```powershell
.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.procesar_lotes `
  --dataset-dir vision/experiments/AGROP42/dataset_work_v1 `
  --output-dir vision/experiments/AGROP42/procesamiento_sin_vistas_v1 `
  --repeats 3 --no-previews
```

### 3. Revisar resultados

```powershell
$r = Get-Content vision/experiments/AGROP42/procesamiento_lotes_v1/summary.json -Raw -Encoding UTF8 | ConvertFrom-Json
$r.status
$r.processed_unique_sha256
$r.products | ConvertTo-Json -Depth 6
$r.excluded_records | ConvertTo-Json -Depth 6
$r.comparison | ConvertTo-Json -Depth 6
```

Los 19 archivos de Work produjeron, en una **prueba aislada de esta implementación**:
4 análisis exploratorios mango y 15 tomate, sin archivos excluidos. La salida y los
tiempos concretos dependen de tu equipo, versión Python/Pillow y disco; no deben
copiarse como mediciones del hardware ESP32.

### Tiempos y evaluación

Cada repetición incluye lectura del archivo, SHA256, decodificación PNG/JPEG,
segmentación cromática y máscaras. No incluye la captura física, anotación por
operador, generación de vistas PNG ni entrenamiento/inferencia de modelo ligero.
Las métricas (`median_ms`/`p95_ms`) se indican **por producto**, junto a una descripción
explícita del equipo ejecutor. Memoria de pico queda `no_medido` (no se inventa RSS).

No hay aún accuracy, precision, recall, F1 ni comparación del mismo conjunto de prueba,
porque la auditoría 01 detecta falta de identidades/sesiones y etiquetas revisadas.
La evaluación de si conviene entrenar debe basarse en esos requisitos y en la
posterior adquisición de un dataset verdaderamente independiente y anotado.

## Entregables versionables

- `vision/evaluation/agrop42/procesar_lotes.py`
- `vision/tests/test_agrop42_batch.py`
- Este documento.

La carpeta `vision/experiments/` es **local y está ignorada**. No subir fotografías
externas o manifiestos con procedencia/licencias hasta revisarlos por separado.
