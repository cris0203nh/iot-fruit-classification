# AGROP-40 — Incremento 02: propuestas de superficie visible

## Fuente y alcance

Se basa en la rúbrica documental del mango Kent `kent-ext-v0.5` (AGROP-13), todavía pendiente de validación especializada, y en el pipeline v0.1 proporcionado para AGROP-40. Mantiene el calibre R02 separado del análisis RGB y **no asigna etiquetas E0/E1/E2 automáticamente**.

El incremento introduce un **localizador experimental de regiones cromáticas** sobre fondo de fotografía aproximadamente neutro. Propone cajas delimitadoras y medianas RGB **sin atribuirlas automáticamente a un mango**, sin clasificar defectos, sin inferir atributos internos y sin declarar la cobertura del fruto completa.

## Procedimiento reproducible

Desde la raíz del repositorio, con Pillow instalado en `backend/.venv`:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s vision/tests -p "test_*.py" -v
.\backend\.venv\Scripts\python.exe -m vision.src.mango_pipeline --manifest vision/experiments/mi_mango.json --output vision/experiments/resultado_mango_superficie.json --preview-dir vision/experiments/vistas
Get-Content vision/experiments/resultado_mango_superficie.json -Raw -Encoding UTF8 | ConvertFrom-Json | Select-Object -ExpandProperty images
```

La fotografía original se lee; nunca se modifica. Las vistas de diagnóstico se generan aparte en `--preview-dir`. El campo `images[].surface_analysis` indica si encontró una, varias o ninguna región, coordenadas `bbox_xywh`, proporción visible y mediana RGB. En `criteria.R07.surface_proposals` se copia el mismo resultado exploratorio. `visual_label` permanece `null`.

## Interpretación y limitaciones

- **`single_candidate_unverified`**: una región cromática candidata, sin confirmar que sea un mango.
- **`ambiguous_multiple_regions`**: varias regiones candidatas en la misma fotografía; el algoritmo **no las considera vistas distintas de una misma pieza**.
- **`background_not_supported`**: las esquinas no justifican asumir un fondo neutro.
- **`no_candidate`**: no se identificó una región cromática suficiente.
- **`partial_border_region`**: la región toca el borde y puede estar cortada.
- **`ambiguous_many_regions`**: demasiadas regiones; revisar el encuadre.

No calcula área física en cm², color de toda la cáscara, madurez, defectos superficiales, calidad comercial ni métricas de exactitud del detector. R03–R06 siguen como `no_determinable` hasta tener anotaciones independientes y/o un modelo validado. Los umbrales de cromaticidad y superficie son **constantes provisionales para pruebas técnicas**, no reglas agronómicas de la rúbrica.

Las pruebas de componentes usan imágenes geométricas sintéticas y no demuestran sensibilidad/especificidad con mangos reales. La fotografía local `I-000004` puede incluir dos vistas en un solo archivo: comprobar visualmente si las cajas corresponden a esos paneles, y conservar el estado de cobertura `null` si no hay protocolo verificado.

El script no modifica `backend/`, `frontend/`, AGROP-39 ni la base SQLite. No incluir en commits el contenido de `vision/experiments/` ni fotografías privadas. El identificador de foto, la variedad Kent declarada y cualquier verificación de calidad se deben documentar con procedencia real.
