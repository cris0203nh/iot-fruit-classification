# AGROP-42 [AG-034] — Incremento 14: comparación de calidad E0/E1/E2

**Motivo del incremento:** Los incrementos 09–13 documentaron el estudio de identidad de producto mango/tomate, la revisión documental de E0/E1/E2 y el protocolo físico. **La exactitud del clasificador de identidad NO equivale a clasificación de la condición externa.** Este incremento prepara un experimento distinto que *solo* funciona con evidencias de calidad externa etiquetadas por producto.

## Alcance realizado en software

- Comparación reproducible **por separado para mango Kent declarado y tomate**, de una regla clásica RGB unidimensional (centroides por clase) frente a un modelo ligero softmax de 3 clases, usando idénticos descriptores y conjuntos de prueba.
- Descriptores técnicos de ROI declarada como verificada: medias/desviaciones RGB, proporciones de canales, forma de ROI, contraste de luminancia, proporción de bordes fuertes y regiones oscuras. **No se confunden descriptores con lesiones reales; su relevancia debe validarse contra rúbrica.**
- Exigencia de referencias de revisor, fecha con zona horaria, rúbrica, archivos de respaldo de etiqueta e identidad/sesión, foto original y SHA256; verifica presencia e integridad digital, **no** autenticidad independiente ni competencia del revisor.
- Exclusión explícita de mango Ataulfo del alcance `kent-ext-*`; no convierte fotos externas anteriores en Kent ni en ground truth.
- Consolidación por pieza (múltiples vistas dan **una observación por pieza**), agrupación de componentes que comparten sesión o pieza, split por grupos para evitar fuga entre entrenamiento, validación y prueba.
- Bloqueo por insuficiencia si falta alguna de las clases E0/E1/E2, no hay al menos 5 componentes pieza/sesión por clase, o no puede generarse una partición con tres piezas de train y una de validación/test por clase. **Estos mínimos son operativos de este experimento, no validación estadística ni un estándar agronómico.**
- Métricas por pieza: matriz de confusión, accuracy, precision/recall/F1 por clase y F1 macro; decisión provisional según F1 macro en validación, nunca basada en seleccionar el mejor resultado de prueba.
- Informe JSON de salida; no sobrescribe informes anteriores. Indicadores de **integración productiva** y **cierre total AG-034** permanecen en `false` incluso en un experimento provisional con datos completos.

## Qué NO resuelve sin evidencia externa

1. No acredita por sí mismo revisión independiente de etiquetas E0/E1/E2 ni aprobación formal de rúbricas.
2. No añade fotografías propias ni variedad Kent confirmada. La fuente externa Ataulfo estudiada antes sigue fuera de la evaluación Kent.
3. No demuestra detección fiable de defectos (R03–R06) ni generalización: un benchmark con pocas sesiones es únicamente exploratorio.
4. No realiza medición de rendimiento en estación física ni pruebas de ESP32/cámara; eso continúa en las 7 fichas del Incremento 13.
5. **No modifica** los pipelines de mango/tomate para asignar calidad automáticamente ni los endpoints FastAPI/React; eso requiere evidencia y corresponde a integración posterior (AG-041 / Sprint 12).

## Datos de entrada

La plantilla `AG034_plantilla_calidad_externa.csv` contiene únicamente las columnas y **ninguna etiqueta ficticia**. Una fila es una vista de una pieza. Formato UTF-8 CSV:

| Campo | Contenido |
|---|---|
| `producto` | `mango` o `tomate` |
| `variedad_declarada` | `Kent` para mango; otro valor para tomate |
| `pieza_id`, `sesion_id` | Identificadores verificados por el responsable de captura, no etiquetas artificiales |
| `imagen_relativa` | Ruta dentro de `--raiz-imagenes` con `/` |
| `sha256_imagen` | SHA256 de los bytes originales JPG/PNG |
| `roi_xywh` | JSON de `[x,y,ancho,alto]` en píxeles de imagen orientada (EXIF) |
| `roi_verificada` | `si` solamente después de revisar manualmente ROI y pieza |
| `estado_revision` | `pendiente`, `no_evaluable`, `revisada_sin_etiqueta` o `etiquetada` |
| `etiqueta_e0_e1_e2` | Solo `E0`, `E1` o `E2` si el registro está `etiquetada` |
| `revisor_id`, `fecha_revision_iso` | Identidad trazable del humano y fecha ISO8601 con zona horaria |
| `rubrica_version` | `kent-ext-*` o `tomato-ext-*`; debe validarse la aprobación de versión por separado |
| `soporte_revision_relativo` | Archivo sustentatorio dentro de `--raiz-soportes` |
| `soporte_identidad_sesion_relativo` | Registro de la pieza y sesión dentro de `--raiz-soportes` |

El archivo no está diseñado para importar directamente las 30 fichas del Incremento 12. Esas fichas son de procedencia externa **y no están acreditadas**. Si se desea usar información de ellas, primero se requiere una fuente adecuada, trazabilidad real y nuevas evidencias revisadas sin modificar los respaldos históricos.

## Ejecutar en Windows PowerShell (raíz del repositorio)

```powershell
$python = '.\backend\.venv\Scripts\python.exe'
& $python -m unittest discover -s vision/tests -p 'test_*incremento14.py' -v

$trabajo = "$env:USERPROFILE\Documents\AgroScan_AG034_Calidad"
New-Item -ItemType Directory -Force -Path "$trabajo\imagenes", "$trabajo\soportes" | Out-Null
Copy-Item 'vision\evaluation\agrop42\AG034_plantilla_calidad_externa.csv' "$trabajo\etiquetas.csv" # Una sola vez: no sobreescribir ficha ya iniciada

& $python -m vision.evaluation.agrop42.comparar_calidad_ag034 `
  --csv "$trabajo\etiquetas.csv" `
  --raiz-imagenes "$trabajo\imagenes" `
  --raiz-soportes "$trabajo\soportes" `
  --salida "$trabajo\AG034_resultado_calidad_01.json"
```

Con el CSV vacío de plantilla, la salida correcta es `bloqueado_por_datos_insuficientes` en ambos productos, con `metricas: null`, **no una nota de exactitud**. Para nuevas ejecuciones elegir otra ruta `--salida`. No subir datos reales, archivos de soporte ni identificadores personales a GitHub sin revisión previa de privacidad, consentimiento y licencia.

## Cierre del alcance hasta AG-034

La plataforma cuenta con **código para evaluar** tres grados de calidad si se aporta material elegible; no cuenta actualmente con un dataset E0/E1/E2 acreditado ni con la calibración y pruebas de hardware pendientes. Por tanto, **AG-034 mantiene cierre parcial**, y el siguiente paso verificable es recopilar/revisar esas evidencias, no marcar automáticamente la actividad como Done.
