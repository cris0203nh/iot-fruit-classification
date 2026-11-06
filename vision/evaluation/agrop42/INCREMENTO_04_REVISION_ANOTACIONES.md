# AGROP-42 [AG-034] — Incremento 04: revisión y anotación trazable

**Alcance:** registrar una revisión humana por imagen de `dataset_work_v1` y exportar
**declaraciones documentales** compatibles con `auditar.py`. No entrena modelos ni
modifica AGROP-39/40/41, fotografías originales, inventario, base SQLite o las
rúbricas. **Ningún campo se completa automáticamente con E0/E1/E2.**

## 1. Generar las fichas editables (Windows PowerShell)

Desde la raíz del repositorio, con los parches AGROP-42 01, 01A, 02 y 03 aplicados:

```powershell
.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.revisar_anotaciones iniciar `
  --dataset-dir vision/experiments/AGROP42/dataset_work_v1 `
  --output vision/experiments/AGROP42/revisiones_pendientes_v1.csv
```

Se esperan **19 filas pendientes** (4 mango y 15 tomate), sin `etiqueta_visual`,
`revisor_id`, pieza ni sesión afirmados. Abre el CSV en Excel/LibreOffice y guarda
como **CSV UTF-8** sin cambiar nombres, orden ni valores de columnas protegidas.
Si Excel cambia un SHA256, el validador rechazará esa fila. Evita copiar datos de
identificación inventados de muestras descargadas de internet.

## 2. Revisar imágenes, una por una

Puedes ver los originales bajo `vision/experiments/AGROP42/dataset_work_v1/images/`
(la columna protegida `archivo` indica la ruta de cada uno), o los diagnósticos
bajo `vision/experiments/AGROP42/procesamiento_lotes_v1/previews/`.
Las máscaras y propuestas de regiones son experimentales; **no son verdades terreno**.

- **Sin revisar:** mantener `estado_revision=pendiente`; no colocar revisor, clase,
  identificación física o sesión. Se admite solo una nota de preparación.
- **Revisada descriptivamente:** `estado_revision=revisada`, `revisor_id`,
  `revisado_en` en ISO 8601 con zona (ej. `2026-11-05T18:30:00-05:00`),
  `rubrica_version` (`kent-ext-v0.5` para mango; `tomato-ext-v0.1` para tomate)
  y `nota_revision`. Puede quedarse **sin clase** E0/E1/E2. Registra
  `observacion_r03` a `observacion_r07` (mango) o a `observacion_r09` (tomate)
  según los aspectos que efectivamente se vean; deja en blanco los demás.
- **No evaluable / excluida:** elegir `estado_revision=no_evaluable` o
  `excluida`, rellenar datos de revisión y `motivo_no_evaluable`. Nunca colocar
  E0/E1/E2. Estas filas quedan en el informe, **fuera** de los manifiestos de
  fotografías candidatas a auditoría supervisada.
- **Clase manual (solo si realmente sustentable):** para `etiqueta_visual=E0/E1/E2`
  es obligatorio `estado_revision=revisada`, `etiqueta_documentada=si`,
  `calidad_confirmada=si`, `cobertura_confirmada=si`, al menos una observación de
  criterio y `justificacion_etiqueta`. Para mango, además,
  `variedad_verificada=si` y `evidencia_variedad` verificable. Estas son
  **afirmaciones del revisor**, no reconocimiento automático ni certificación
  independiente. La rúbrica Kent v0.5 sigue sin validación experta final.
- **Identidad de pieza física / sesión:** si no se conoce por una bitácora de
  captura o registro de la fuente, **dejar sin confirmar**. `pieza_confirmada=si`
  exige lote, pieza y `evidencia_pieza`; `sesion_confirmada=si` exige además
  identificador de dispositivo, sesión y `evidencia_sesion` (no inventar estos
  datos usando nombres de archivo, URL o fotografías). Solo las declaraciones
  documentadas se transfieren a nuevos manifiestos para su auditoría.
- **Posibles duplicados visuales:** el importador marca pares sospechosos por
  dHash. No son duplicados confirmados. Si se intenta afirmar que son piezas
  físicas diferentes, se exige revisión del par y
  `revision_similitud=distintas_piezas` + `evidencia_similitud` en ambas fichas.
  Pueden utilizarse también `misma_pieza` o `pendiente`, sin inferir identidad
  automáticamente.

**Advertencia:** las 19 imágenes recopiladas de internet no proporcionan
identidad/sesión de captura verificables en el registro actual. Registrar
observaciones visuales no las convierte en 19 piezas independientes ni prueba
que sus etiquetas sean correctas. Una fotografía con varias frutas no puede
marcarse como la evaluación completa de una pieza sin resolver la ambigüedad.

## 3. Validar y exportar una versión NUEVA

```powershell
.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.revisar_anotaciones validar `
  --dataset-dir vision/experiments/AGROP42/dataset_work_v1 `
  --revisiones vision/experiments/AGROP42/revisiones_pendientes_v1.csv `
  --output-dir vision/experiments/AGROP42/revision_documentada_v1
```

La salida **no debe existir previamente**. No sobrescribir: usa `v2` en una nueva
revisión. Contiene:

- `summary.json`: totales pendientes/revisados/no evaluables/excluidos,
  descriptores de viabilidad y limitaciones explícitas.
- `revisiones_documentadas.json`: declaraciones individuales, observaciones
  por criterio, fuente y justificaciones.
- `annotations_to_review.json`: solo etiquetas declaradas, con SHA256,
  revisor/fecha/rúbrica. **No certifica experto ni verdad terreno.**
- `manifests/*.json`: rutas a imágenes originales (sin copiarlas); pieza/sesión
  solo si se declararon documentalmente. Fotografías excluidas/no evaluables no
  se exportan a manifiestos candidatos.

El validador rechaza mutaciones del SHA, fotos alteradas, cambio de producto,
archivos faltantes, rúbrica incompatible, clase sin revisión, evidencias de
pieza/sesión ausentes, etiquetas contradictorias y reasignaciones de un mismo
archivo a piezas físicas diferentes. No permite generar el paquete dentro del
dataset original.

## 4. Volver a auditar; no confundir la salida con entrenamiento

```powershell
.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.auditar `
  --manifests-dir vision/experiments/AGROP42/revision_documentada_v1/manifests `
  --annotations vision/experiments/AGROP42/revision_documentada_v1/annotations_to_review.json `
  --output vision/experiments/AGROP42/auditoria_revision_v1.json
```

El auditor además consulta el SQLite local, de existir. **No incluir en la misma
ejecución los manifiestos antiguos de `dataset_work_v1` y los nuevos**, pues se
duplicarían registros de fotografías. El ZIP externo no se incorpora a Git.

```powershell
$r = Get-Content vision/experiments/AGROP42/revision_documentada_v1/summary.json -Raw -Encoding UTF8 | ConvertFrom-Json
$r.status
$r.estados_revision
$r.anotaciones_exportadas_para_auditoria

$a = Get-Content vision/experiments/AGROP42/auditoria_revision_v1.json -Raw -Encoding UTF8 | ConvertFrom-Json
$a.status
$a.por_producto | ConvertTo-Json -Depth 5
```

Cuando todas las filas permanecen pendientes (flujo inicial **probado con el ZIP
de 19 fotos**), el resultado es `sin_revisiones_efectuadas`, **cero etiquetas**,
19 manifiestos sin sesión y auditoría `bloqueado_por_datos_insuficientes`.
Esto es un resultado técnico correcto, no un fallo ni una aprobación agronómica.

## 5. Pruebas y control de versiones

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s vision/tests -p "test_*.py" -q

git status -sb
git -c core.whitespace=cr-at-eol diff --check
```

Este incremento agrega **35 pruebas** de validación de datos, bloqueo de clases
insuficientemente documentadas, trazabilidad, integración con el auditor y
protección frente a sobrescritura. Si conservas las 126 pruebas del incremento
anterior, el total esperado es **161**, sujeto a confirmación en tu Windows.
No subir fotografías, CSV rellenados con datos personales, informes locales ni
bases de datos; `vision/experiments/` está excluido del control de versiones.

### Criterio de terminación

**Incremento 04 implementado** significa que existe un procedimiento reproducible
para revisar/anotar con evidencia y detectar información insuficiente. No significa
que las fotos de Work hayan sido revisadas, que un modelo esté entrenado ni que
AGROP-42 cumpla ya su comparación de precisión con un mismo conjunto de prueba.
