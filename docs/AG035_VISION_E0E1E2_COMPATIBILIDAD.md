# AgroScan — AG-035 / AGROP-43 — Incremento 02: métricas visuales E0/E1/E2

## Problema resuelto en software

`backend/metrics/evaluate_performance.py` evalúa `primera/segunda` (clasificación **comercial** en su contrato original); AG-034, AG-036 y AGROP-15 v0.2 emplean `E0/E1/E2` para **condición visual externa**. **No existe una equivalencia aprobada** entre ambas taxonomías.

Este incremento añade una **vía explícita y separada** `backend/metrics/evaluate_visual_quality.py` sin cambiar `evaluate_performance.py`, sus reportes o tests existentes. No se realizan conversiones automáticas, no se atribuyen etiquetas reales a fotografías, ni se equipara la detección de YOLOE con la clasificación visual E0/E1/E2.

Las rúbricas de origen son propuestas: `kent-ext-v0.4` y `tomato-ext-v0.2` en los documentos AGROP-13/14/15. Se requiere aprobación práctica por personal responsable y validación de evidencias. Versiones posteriores no son equivalentes automáticamente; el script rechaza mezclar versiones de rúbrica del mismo producto.

## Contrato de entrada

Archivo JSON: una **lista** de objetos (una observación *consolidada por pieza física*, no por vista). La plantilla distribuida es `[]`, sin predicciones ni resultados inventados.

| Campo | Requisito |
|---|---|
| `sample_id` | Identificador único de muestra en este archivo |
| `product` | `mango` o `tomate` |
| `lot_id`, `piece_id` | Claves no vacías; ninguna pieza puede repetirse dentro del mismo producto y lote |
| `variedad_declarada` | En mango: `Kent` declarado; Ataulfo excluido. En tomate se recomienda registrar el tipo real |
| `rubric_version` | `kent-ext-*` para mango; `tomato-ext-*` para tomate, única versión por producto dentro de una ejecución |
| `y_true` | E0, E1 o E2 de revisión humana respaldada (no una predicción de IA) |
| `y_pred` | E0, E1 o E2 generado **por un modelo específico de grado visual**, NO la clase de detección de YOLOE |
| `label_verification` | Literal `verified`; declaración de comprobación externa del dato, no la realiza este código |
| `ground_truth_source` | `AG036_acuerdo_doble` o `AG036_conciliacion` |
| `ground_truth_reference` | Referencia auditable no vacía al registro humano o acta; el script no accede ni autentica ese documento |
| `prediction_source` | Literal `model` |
| `prediction_verification` | Literal `verified`; debe existir respaldo de la salida/modelo, no supone que la predicción sea correcta |
| `source_model_version` | Identificador no vacío del clasificador visual que emitió `y_pred` |
| `source_status` | Opcional; si se indica, `completed` o `evaluated`, nunca `processing` o `error` |
| `confidence` | Opcional, valor finito entre 0 y 1, o `null`; **no** representa exactitud |

### Limitaciones de integridad y aprobación

- Una bandera `verified` y un identificador de acta **son afirmaciones del archivo de entrada**. Se comprueba el contrato, **no** la identidad de revisores, su independencia, el contenido o la autenticidad del soporte, la aprobación de la rúbrica ni la vigencia del modelo.
- Cuando una pieza está repetida por vistas o muestras se excluyen **todas sus filas duplicadas**; primero hay que consolidar las vistas en un solo registro y revisar etiquetas/identificadores.
- Si un producto contiene varias versiones de rúbrica en entradas que pasarían los demás controles, el programa excluye esas filas de las métricas por ese producto y explica por qué. Evaluar versiones por separado.
- Las fotografías externas de mango Ataulfo no se consideran Kent. La rúbrica de tomate debe confirmar el tipo piloto antes de hacer afirmaciones de generalización.
- AG-036 mide **concordancia entre dos revisores** mediante porcentaje de acuerdo y kappa. AG-035 mide **rendimiento de un modelo frente a etiquetas humanas de referencia**, usando matriz de confusión y F1: son fenómenos distintos.
- `macro_f1_clases_presentes` resume solo grados con soporte real; `macro_f1_tres_clases` se devuelve `null` si falta algún grado, evitando presentar una evaluación parcial como cobertura completa.

## Cómo ejecutarlo en PowerShell

En raíz del repositorio:

```powershell
Push-Location backend
$py = '.\.venv\Scripts\python.exe'
& $py -m unittest discover -s tests -p 'test_agrop43*.py' -q

$carpeta = Join-Path $env:USERPROFILE 'Documents\AgroScan_AG035_Visual'
New-Item -ItemType Directory -Force -Path $carpeta | Out-Null
$entrada = Join-Path $carpeta 'entrada_visual.json'
if (-not (Test-Path $entrada)) { Copy-Item '.\metrics\AG035_entrada_visual_plantilla.json' $entrada }
& $py -m metrics.evaluate_visual_quality --input $entrada --output (Join-Path $carpeta 'reporte_visual_01.json')
Pop-Location
```

Para una ejecución posterior usar otra ruta `--output`: el script **no sobrescribe** informes existentes. Con la plantilla vacía, los resultados deben ser `insufficient_data`, cero casos evaluables y métricas `null`.

El informe incluye resultados separados para mango/tomate, precisión, recall y F1 por E0/E1/E2, matriz de confusión 3×3, F1 macro cuando procede, cobertura y exclusiones con motivo. Su estado es siempre *exploratorio, pendiente de verificación externa* cuando hay registros que cumplen el contrato; no certifica resultados agronómicos.

## Dependencias y cierre

- **AG-036:** obtener las dos revisiones independientes y la conciliación documentada por lote y pieza. El informe AG-036 por sí solo **no** se transforma automáticamente en ground truth; requiere vincular sus dictámenes humanos a los registros finales después de revisión.
- **AG-034:** un detector YOLOE que identifica mango/tomate **no produce** una predicción E0/E1/E2. Para AG-035 visual debe existir una salida de un modelo de grados externos, con trazabilidad y conjunto de prueba válido.
- **AG-035:** las entradas históricas publicadas de AGROP-43 contenían 18 registros sin etiquetas verificadas ni predicciones válidas; **no** convertirlos en métricas mediante un cambio de nombre.
- No marcar AG-035 ni AG-036 como Done únicamente por instalar este incremento. Requieren datos, revisión humana y evidencias de ejecución.

**Archivos incorporados:** `backend/metrics/evaluate_visual_quality.py`, `backend/metrics/AG035_entrada_visual_plantilla.json`, `backend/tests/test_agrop43_visual_quality.py`, este documento.
