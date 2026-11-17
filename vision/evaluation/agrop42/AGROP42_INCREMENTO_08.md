# AGROP-42 — Incremento 08: evaluación técnica de regiones, máscaras y RGB

## Alcance

Se agrega `vision.evaluation.agrop42.evaluar_rgb_incremento08`, un **banco de pruebas descriptivo** para las ingestas externas del Incremento 07. No sustituye `mango_pipeline.py` (AGROP-40), `tomato_pipeline.py` (AGROP-41), sus rúbricas ni el auditor de elegibilidad de AGROP-42. Reutiliza los módulos existentes:

- `vision.src.surface_analysis.propose_surface_regions` — propuestas de regiones por contraste cromático con fondo neutro.
- `vision.src.surface_masks.describe_surface_masks` — máscaras cromáticas no verificadas, píxeles y cuantiles RGB excluyendo píxeles fuera de las máscaras candidatas.
- `vision.src.tomato_surface.analyze_tomato_surface` — adaptador específico de tomate.
- `save_candidate_preview` / `save_mask_preview` — visualizaciones de diagnóstico, sin modificar originales.

**El mango no se trata como Kent**: la fuente externa del paquete de 90 vistas lo declara Ataulfo. Las fotografías de tomate incluyen 12 vistas con alguna dimensión inferior a 128 px. El experimento solo describe color superficial *provisionalmente segmentado*.

## Requisitos

- Ejecutar desde la raíz del repositorio, con el entorno Python que tenga Pillow instalado (`vision/requirements.txt`).
- Usar una carpeta de salida **nueva**, separada de la ingesta verificada. No se sobrescriben resultados existentes.
- La entrada debe proceder de `ingestar_fuentes_externas importar` del Incremento 07, incluidos `inventario_externo.csv`, `control_externo.json` y `originales/`.

## Comandos Windows (PowerShell)

```powershell
# Ajustar si utilizaste otra carpeta de ingesta del Incremento 07.
$ingesta = "$env:USERPROFILE\Documents\AgroScan_Fuentes_Externas\ingesta_001"
$analisis = "$env:USERPROFILE\Documents\AgroScan_Fuentes_Externas\analisis_rgb_08"

.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.evaluar_rgb_incremento08 evaluar `
  --ingesta "$ingesta" `
  --salida "$analisis" `
  --previews-por-ejemplar 1

.\backend\.venv\Scripts\python.exe -m vision.evaluation.agrop42.evaluar_rgb_incremento08 verificar --salida "$analisis"

.\backend\.venv\Scripts\python.exe -m unittest vision.tests.test_agrop42_rgb_incremento08 -v
.\backend\.venv\Scripts\python.exe -m unittest discover -s vision/tests -p "test_*.py" -q
```

`--previews-por-ejemplar`: 0 (sin PNG), 1 (primera vista de cada ID), 2 o 3. Los 2 PNG de cada vista elegida son imagen con cajas y máscara provisional. Para generar de nuevo usar una carpeta de salida distinta: no se borra ni sobreescribe automáticamente.

## Salidas

| Archivo | Contenido | Cómo interpretarlo |
|---|---|---|
| `informe_tecnico.json` | Conteos por especie, estados, SHA de artefactos | Auditoría técnica, no evaluación de exactitud |
| `resultados_por_vista.csv` | 1 registro por fotografía, propuesta de región, segmentación cromática y RGB de candidato principal | Candidato principal = segmento con más píxeles, no corresponde necesariamente al fruto |
| `resultados_por_ejemplar.csv` | Agrupación *por identificador declarado por fuente* de las tres vistas y mediana de medianas RGB | No demuestra identidad física de 3 vistas ni independencia de sesión |
| `revision_mascaras_pendiente.csv` | Plantilla para revisar manualmente región, fondo, calidad y eventual etiqueta | Se entrega sin campos de aprobación completados |
| `previews/` | Cajas y máscaras diagnósticas PNG | Nunca se escriben sobre los originales |

`mediana_rgb_mascara`, `p10_rgb_mascara` y `p90_rgb_mascara` se calculan únicamente cuando hay al menos una región cromática candidata y se refieren a **píxeles detectados**. Una celda vacía indica que el método no pudo obtener un segmento; no se completa con valores de la imagen completa. El conteo `fotos_con_mascara_candidata` expresa disponibilidad técnica, no exactitud de segmentación ni *IoU* o *Dice* (no existe ground truth de máscara).

Los estados `single_candidate_unverified`, `partial_border_region`, `ambiguous_multiple_regions`, `no_candidate` y `background_not_supported` son **diagnósticos heurísticos**. No son etiquetas de calidad, madurez ni enfermedad.

## Comprobaciones y reglas de integridad

- Valida la existencia y tipo de procedencia externa/no autorizada para entrenamiento del `control_externo.json`.
- Recalcula el SHA-256 de cada original, comprueba dimensiones y evita archivos duplicados, rutas `..`, rutas absolutas y rutas Windows.
- Rechaza etiquetas comerciales agregadas al inventario de ingesta sin revisión acreditada.
- Mantiene los tres registros de vista agrupados bajo el ID declarado del ejemplar; **cero grupos independientes verificados**.
- Procesa primero en carpeta temporal; tras éxito la mueve a la ruta nueva, sin tocar `originales/`.
- `verificar` comprueba SHA-256 de los CSV y PNG generados.

## Resultado de referencia: 90 vistas del paquete aportado

Este incremento se ejecutó sobre el artefacto externo ya verificado con 45 fotografías de mango y 45 de tomate:

| Resultado | Mango (45) | Tomate (45) |
|---|---:|---:|
| Vistas con al menos una máscara cromática candidata | 35 | 44 |
| Propuestas de región única no confirmada | 35 | 8 |
| Región que toca el borde | 0 | 35 |
| Fondo no soportado | 10 | 0 |
| Múltiples regiones ambiguas | 0 | 1 |
| Sin componente candidato | 0 | 1 |
| Vistas menores de 128 px | 0 | 12 |
| Regiones confirmadas por operador | 0 | 0 |

Los datos del informe y la ejecución Python son mediciones **del baseline cromático**, no indicadores de rendimiento de un clasificador. El estado de AGROP-42 sigue condicionado a revisión de máscaras, etiquetas y grupos con evidencias.

## Próximos criterios de avance

1. Revisar en `revision_mascaras_pendiente.csv` las imágenes críticas: mango con fondo no soportado y tomate con máscara al borde, sin completar automáticamente etiquetas.
2. Incorporar la confirmación humana explícita de la región/mascara por SHA y vista, junto con motivo y responsable.
3. Mantener fuera de entrenamiento los registros externos cuyos derechos, piezas, sesiones o etiquetas no se acrediten.
4. Para una comparación real de E0/E1/E2, recopilar mango Kent y tomate controlados, más etiquetas revisadas, partituras por pieza/sesión, máscaras de referencia si se desean IoU/Dice y un protocolo de métricas de prueba independiente.
