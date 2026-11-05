# AGROP-40 / AG-032 — Incremento 03: máscaras cromáticas de superficie visible

**Versión experimental:** `agrop40-mango-provisional-masks-v0.3`
**Rúbrica documental:** `kent-ext-v0.5` (AGROP-13; no aprobada como v1.0).
**Base:** incremento 02, que detecta cajas candidatas en fotografías con fondo aproximadamente neutro.

## Objetivo verificable

Construir máscaras **provisionales** que excluyan parte del fondo gris de los descriptores cromáticos. En cada región candidata, registrar la máscara en resolución de procesamiento (lado mayor ≤512 píxeles), medianas RGB, percentiles 10/90 por canal, porcentaje de píxeles de máscara respecto a la caja, y un PNG de diagnóstico opcional.

No es un modelo entrenado ni una segmentación anotada/validada. Zonas poco saturadas de la fruta pueden omitirse; pueden incluirse artefactos, reflejos o pedúnculo. **La selección manual de una máscara no confirma que dos regiones sean vistas de la misma pieza**, ni garantiza la exactitud de atributos agronómicos.

Los criterios R03–R06 permanecen `no_determinable`. No se generan etiquetas E0/E1/E2, diagnósticos de enfermedades, estimaciones de madurez interna, equivalencias comerciales ni área física en cm². R02 permanece ligado a un pesaje verificado, no a píxeles.

## Ejecución sobre la fotografía local ya registrada

Desde la raíz de `iot-fruit-classification`, con el manifiesto existente `vision/experiments/mi_mango.json`:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s vision/tests -p "test_*.py" -v
.\backend\.venv\Scripts\python.exe -m vision.src.mango_pipeline --manifest vision/experiments/mi_mango.json --output vision/experiments/resultado_mango_mascara.json --mask-preview-dir vision/experiments/mascaras
$r = Get-Content vision/experiments/resultado_mango_mascara.json -Raw -Encoding UTF8 | ConvertFrom-Json
$r.images[0].mask_analysis | ConvertTo-Json -Depth 10
Start-Process .\vision\experiments\mascaras\01_I-000004_mascara.png
```

Los archivos generados están en `vision/experiments/`, ignorado por Git (agregado en incremento 02). Las fuentes y la base de datos no se modifican.

## Selección manual opcional y trazable

Solo **después de revisar personalmente** la imagen de diagnóstico puede añadirse a un elemento de `images[]`:

```json
"surface_selection": {
  "candidate_indices": [1],
  "reviewed_by_operator": true,
  "review_note": "Se revisó visualmente la región candidata 1 de esta fotografía; no se ha verificado cobertura global."
}
```

- `candidate_indices` son números de la **propuesta actual**, no identificadores persistentes de frutos.
- La nota de revisión es obligatoria y no debe contener afirmaciones no verificadas.
- `operator_selected_provisional_masks` solo indica que se declaró una selección; **no** valida la especie, la identidad de pieza, la relación entre dos vistas ni la segmentación.
- No usar `candidate_indices:[1,2]` para declarar que se trata de la misma pieza si no existe evidencia independiente.
- Cambios en algoritmo o imagen pueden alterar la numeración: volver a inspeccionar antes de seleccionar.

## Contrato nuevo (sin cambios de backend)

`images[].mask_analysis` y `criteria.R07.provisional_surface_masks[]` contienen:

- `method`: algoritmo/versionado.
- `status`: `pending_operator_selection`, `operator_selected_provisional_masks` o `unavailable`.
- `segments[]`: `candidate_index`, `bbox_xywh`, `pixel_count_processing`, `pixel_fraction_of_processing_image`, `mask_fill_fraction_of_bbox`, `masked_median_rgb`, `masked_rgb_p10`, `masked_rgb_p90`, `selected_by_operator`.
- `assignment_of_regions_to_piece: not_verified` y `requires_independent_validation: true`.

Los descriptores son de **píxeles cromáticos seleccionados heurísticamente**, no de la superficie física total del fruto. Por eso, la máscara se guarda solamente como vista de diagnóstico, no como evidencia de una clasificación.

## Pruebas y evidencia

Se amplía la suite de 19 a 30 pruebas con casos de componentes sintéticos, fondo neutro, máscaras separadas, cálculo RGB sin tomar la caja entera, validación de selecciones manuales, ausencia de candidatos, CLI determinista y garantía de no sobrescribir imágenes originales. Estos resultados prueban el software, **no** tasas de acierto, sensibilidad, especificidad ni aptitud comercial. Para validar detección de defectos se requiere dataset anotado independiente, definición de referencia, acuerdo entre evaluadores y experimentos propios de AGROP-38/39/42/43/44.
