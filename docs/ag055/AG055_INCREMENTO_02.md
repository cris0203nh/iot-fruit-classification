# AG-055 / AGROP-67 — Incremento 02: preparación y consolidación del dataset real

## 1. Objetivo y límites

Auditar la procedencia e integridad de fotografías y etiquetas de **AG-036** y preparar las
entradas experimentales E0/E1/E2 que consume **AG-034 / AG-055 I01**. Este incremento no
reclasifica imágenes, no inventa anotaciones ni realiza entrenamiento con datos insuficientes.

El universo AG-036 v2 documentado tiene 97 vistas; el revisor A reportó 30 piezas
(15 de mango y 15 de tomate), con distribución total 25 E0, 2 E1, 3 E2.
**Son cifras documentadas previamente, no una verificación de tus archivos locales**;
la ejecución calcula los recuentos efectivos a partir de tus fuentes.

AG-036 reporta una **etiqueta por pieza** y varias vistas por pieza; AG-034 requiere
además una **ROI por vista** revisada, imagen JPG/PNG intacta, identidad/sesión,
rúbrica, soporte de etiqueta y derechos de uso. No se da por validada ninguna ROI
por el solo hecho de tener una etiqueta del revisor A.

**Las pruebas con imágenes sintéticas comprueban software, nunca calidad agronómica.**

## 2. Archivos añadidos

- `vision/ag055/dataset_i02.py`: `inventariar` y `consolidar`, sin tocar I01.
- `vision/tests/test_ag055_dataset_i02.py`: pruebas aisladas de contratos y barreras.
- `docs/ag055/AG055_INCREMENTO_02.md`: ejecución y criterios de aceptación.

No se modifican archivos de AG-034, AG-036, AG-054, backend, React, ni SQLite.
No se crea ninguna migración. No se generan carpetas de respaldo.

## 3. Etapa A — Inventariar los documentos originales

Desde la raíz del proyecto en Windows PowerShell:

```powershell
$py = '.\backend\.venv\Scripts\python.exe'
$universo = "$env:USERPROFILE\Documents\AgroScan_AG036_08\universo_01\universo_AG036_v2.csv"
$imagenes = "$env:USERPROFILE\Documents\AgroScan_AG036_Multifuente_v2\imagenes"
$devolucion = "$env:USERPROFILE\Downloads\AG036_Devolucion_A.zip"
$base = "$env:USERPROFILE\Documents\AgroScan_AG055_Dataset"
New-Item -ItemType Directory -Force -Path $base | Out-Null

foreach ($fuente in @($universo, $imagenes, $devolucion)) {
  if (-not (Test-Path -LiteralPath $fuente)) { throw "Falta fuente original: $fuente" }
}

& $py -m vision.ag055.dataset_i02 inventariar `
  --universo $universo --imagenes $imagenes --devolucion-a $devolucion `
  --salida-dir (Join-Path $base 'preparacion_01')
if ($LASTEXITCODE -ne 0) { throw 'Falló inventario de AG-055' }
```

Usar rutas distintas si tus archivos reales se almacenaron en otros directorios.
El script **no crea** `preparacion_01` si no hay datos válidos; cuando se crea,
contiene las tablas y copias exactas de soportes A (no copias de fotografías):

- `AG055_I02_inventario.csv`: todas las vistas verificadas desde el universo, con sus hashes y estados.
- `AG055_I02_fichas_verificacion.csv`: **solo vistas de piezas con etiqueta reportada A**.
- `AG055_I02_fuentes.json`: rutas privadas y hashes de los archivos de origen.
- `AG055_I02_resumen_inicial.json`: conteos del material recibido.
- `soportes/AG036_A/`: archivos reales de soporte del ZIP original; no se modifican.

**No subas la carpeta `preparacion_01` a GitHub**; contiene identificadores y soportes.

## 4. Etapa B — Verificación por vista, antes de entrenar

En `AG055_I02_fichas_verificacion.csv`, el responsable confirma únicamente
las siguientes columnas editables, con evidencia auténtica y coherente:

| Campo | Valor autorizado para promoción | Evidencia necesaria |
|---|---|---|
| `roi_xywh` | `[x,y,ancho,alto]` (píxeles orientados por EXIF) | Region visible de la fruta, inspeccionada manualmente |
| `roi_verificada` | `si` | El responsable revisó esa ROI |
| `derechos_uso` | `permitido` | `soporte_derechos_relativo` (licencia/permiso correspondiente) |
| `identidad_sesion_verificada` | `si` | `soporte_identidad_sesion_relativo` (ficha de identidad y captura) |
| `rubrica_aprobada` | `si` | `soporte_rubrica_relativo` (aprobación real de versión) |
| `variedad_verificada` | `si` para mango Kent | `soporte_variedad_relativo` (evidencia real de variedad) |
| `observacion_verificador` | Texto libre | Motivo de excepciones o problemas |

Los archivos asociados se guardan localmente en `preparacion_01/soportes/`,
por ejemplo `acreditaciones/licencia.pdf`, sin rutas absolutas ni `..`.
**Nunca marques «si» sin la comprobación y archivo correspondiente.**
Los campos de procedencia, etiqueta A, pieza/sesión y SHA-256 están bloqueados;
el script rechaza cualquier cambio en ellos.

La foto v2 original que **sea MPO internamente** se inventaría pero NO se exporta
a AG-034, aunque tenga extensión `.JPG`. Debe generarse y auditarse un derivado
JPG/PNG bajo un procedimiento explícito en un incremento posterior; no
sobrescribir ni alterar el archivo original y su SHA-256.

## 5. Etapa C — Consolidar lo realmente elegible

```powershell
$base = "$env:USERPROFILE\Documents\AgroScan_AG055_Dataset"
& .\backend\.venv\Scripts\python.exe -m vision.ag055.dataset_i02 consolidar `
  --preparacion (Join-Path $base 'preparacion_01') `
  --salida-dir (Join-Path $base 'consolidacion_01')
if ($LASTEXITCODE -ne 0) { throw 'Consolidación AG055 fallida' }
```

Entregables:

- `AG055_I02_etiquetas_elegibles_AG034.csv`: **columnas exactas** del contrato de entrenamiento AG-034; si no hay registros elegibles, contiene solo encabezados.
- `AG055_I02_exclusiones.csv`: razones por cada fotografía no promocionada.
- `AG055_I02_resumen_consolidado.json`: conteos de vistas, piezas y grupos independientes, con déficit frente al mínimo por E0/E1/E2.
- `AG055_I02_informe.md`: lectura breve defendible en Jira.

Las vistas con varias fotos se agrupan en una sola pieza, y las sesiones
compartidas nunca se separan entre train/validación/test. El mínimo de
**5 componentes independientes por grado y por producto** procede del protocolo
experimental AG-034; no constituye criterio de significancia estadística.

**Importante:** una licencia o rúbrica marcada «permitido/si» y respaldada por
archivo es una **declaración auditable**, no autenticación de legitimidad externa.
No se calcula concordancia entre revisores a partir de la revisión A.

## 6. Validación e integración con el Incremento 01

```powershell
$py = '.\backend\.venv\Scripts\python.exe'
& $py -m unittest discover -s vision/tests -p 'test_ag055_dataset_i02.py' -v
Push-Location backend
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_ag055_*.py' -q
Pop-Location
& $py -m vision.ag055.dataset_i02 --help
```

Solo si `consolidacion_01` contiene un conjunto completo y la evaluación metodológica
es satisfactoria, ejecutar **AG-055 I01** (no antes):

```powershell
# Sustituye por una nueva ruta de salida que NO exista.
$base = "$env:USERPROFILE\Documents\AgroScan_AG055_Dataset"
& $py -m vision.ag055.quality_model `
  --csv (Join-Path $base 'consolidacion_01\AG055_I02_etiquetas_elegibles_AG034.csv') `
  --imagenes "$env:USERPROFILE\Documents\AgroScan_AG036_Multifuente_v2\imagenes" `
  --soportes (Join-Path $base 'preparacion_01\soportes') `
  --salida-informe (Join-Path $base 'calidad_experimental_01.json')
```

Si hay menos de 5 grupos independientes de cualquiera de E0/E1/E2 por producto,
el entrenador debe bloquear el producto, sin presentar una exactitud ficticia.
No exportar modelos para despliegue sin revisión y validación separada.

## 7. Criterios de cierre del Incremento 02

1. Carga reproducible de fuente real AG-036: ZIP A + universo + imágenes originales.
2. Recuento de 97/75 vistas y 30 piezas **solo si coinciden con los archivos reales**.
3. No se promueve una ROI, licencia, identidad/sesión, variedad o rúbrica no verificada.
4. Rechazo de modificación de etiquetas originales, cambios SHA y duplicaciones.
5. Exportador final compatible con AG-034/AG-055 I01, con bloqueos honestos.
6. Documentar insuficiencia por grado para orientar capturas/revisiones posteriores.

No cerrar AG-055 global hasta validar clasificación E0/E1/E2 en datos independientes.
