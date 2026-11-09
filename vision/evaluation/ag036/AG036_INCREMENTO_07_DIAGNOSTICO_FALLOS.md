# AgroScan — AG-036 / AGROP-44 — Incremento 07: diagnóstico focalizado de YOLOE

## Objetivo técnico y alcance

Diagnosticar **10 fallos previamente confirmados por revisión humana** en el dataset v2 (97 fotografías) sin reiniciar la toma de datos ni modificar la configuración productiva. Los fallos son **8 mango, 2 tomate**: **7 detecciones con clase inesperada** y **3 casos sin detección**. La selección y los comentarios humanos proceden del CSV consolidado de revisión manual; **no se deducen del modelo**.

Se prueba un único cambio controlado: resolución `imgsz` de YOLOE = **512 (baseline), 640 y 768**, con el mismo `get_vision_model()` que utiliza el backend (`yoloe-26n-seg.pt` más `agroscan_mango_tomato_prompts.npz` cuando está disponible). Las demás opciones siguen fijas: `conf=0.25`, `iou=0.50`, `max_det=10`, `device='cpu'`. **No se entrenan pesos ni se cambian los prompts de producción.**

Se seleccionan por SHA256 10 fallos y **12 controles deterministas**, priorizando representación por producto y fuente. Los controles provienen de imágenes previamente aceptadas automáticamente; **no cuentan con validación humana**. La comparación controla regresiones operativas, pero no mide errores reales ni falsos positivos de esos controles.

## Entradas

1. `AgroScan_AG036_Deteccion_97_v2/resultados_deteccion.csv` — 97 estados históricos de YOLOE.
2. `AG036_07_fallos_confirmados.csv` — 10 revisiones manuales confirmadas, incluidas en el kit privado de evidencias (no se sube a GitHub).
3. `AgroScan_AG036_Multifuente_v2/imagenes` — fotografías originales, verificación SHA256 antes de cada ejecución.

## Uso (PowerShell en la raíz del repositorio)

El paquete privado de entradas entrega `AG036_07_fallos_confirmados.csv`; guárdalo en `Descargas`.

```powershell
$py = ".\backend\.venv\Scripts\python.exe"
$detector = "$env:USERPROFILE\Documents\AgroScan_AG036_Deteccion_97_v2\resultados_deteccion.csv"
$fallos = "$env:USERPROFILE\Downloads\AG036_07_fallos_confirmados.csv"
$imagenes = "$env:USERPROFILE\Documents\AgroScan_AG036_Multifuente_v2\imagenes"
$salida = "$env:USERPROFILE\Documents\AgroScan_AG036_Diagnostico_07"

& $py -m vision.evaluation.ag036.diagnosticar_fallos_yoloe `
    --resultados $detector --fallos $fallos --raiz-imagenes $imagenes `
    --salida-dir $salida --modo inferir
```

Para obtener una auditoría de las entradas **sin inferencias** (otra carpeta nueva):

```powershell
& $py -m vision.evaluation.ag036.diagnosticar_fallos_yoloe `
    --resultados $detector --fallos $fallos --raiz-imagenes $imagenes `
    --salida-dir "$env:USERPROFILE\Documents\AgroScan_AG036_Diagnostico_07_Preparar" `
    --modo preparar
```

### Resultados

- `casos_seleccionados.csv`: 10 fallos más 12 controles, con procedencia, SHA256, grupo y hipótesis para revisión.
- `resultados_variantes.csv`: 3 inferencias por fotografía, clase top, confianza, caja del producto esperado, máscara y estado operativo (66 filas).
- `detecciones_completas.jsonl`: candidatos completos, **incluidas las clases no esperadas**, para auditar confusiones mango/tomate.
- `resumen_diagnostico.json`: recuperaciones candidatas, controles que dejan de estar aptos y discordancias del baseline 512.
- `informe_diagnostico.md`: comparativo listo para evidenciar en Jira.

Una **recuperación candidata** sucede cuando una fotografía antes fallida pasa la regla automática de captura; **no demuestra que la caja sea correcta**. Un **retroceso operativo** sucede cuando un control antes apto deja de cumplir la regla. Se requiere inspección visual de cualquier caso que cambie, y validación más amplia antes de trasladar un ajuste a producción.

La reproducción con `imgsz=512` debe compararse con los resultados históricos. Si aparecen discrepancias, comprobar modelo, prompts, dependencias y configuración del entorno antes de interpretar las variantes.

## Pruebas

```powershell
& $py -m unittest discover -s vision/tests -p "test_ag036_diagnostico_fallos_yoloe.py" -q
& $py -m unittest discover -s vision/tests -p "test_ag036_*.py" -q
& $py -m unittest discover -s vision/tests -p "test_*.py" -q
```

## Restricciones y criterio de cierre del incremento

- Las **10 incidencias** quedan identificadas y sus archivos e integridad verificados.
- Se comparan pares por fotografía (512/640/768) y controles sin sobrescribir evidencias históricas.
- Se obtiene la clase efectivamente predicha por el modelo en los fallos con clase inesperada.
- Se reportan posibles mejoras y regresiones sin adjudicar exactitud, recall ni precision.
- La configuración productiva no se modifica ni se autoriza su cambio mediante este incremento.
- La clasificación **E0/E1/E2** sigue pendiente de revisión humana separada.

**Jira:** AGROP-44, Incremento 07: *Diagnóstico de errores de detección YOLOE*. Actualizar historia con resultados reales del ensayo, archivos producidos y PR. Evitar marcar como corregidos los diez fallos hasta ver la nueva evidencia.
