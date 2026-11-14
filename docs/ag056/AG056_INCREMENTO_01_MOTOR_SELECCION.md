# AG-056 — Incremento 01: motor de selección de revisiones humanas

**Estado:** implementado como núcleo puro, validado con pruebas unitarias; **todavía no integrado a una API ni a la bandeja React** (corresponden a I02 e I03). No se ha desplegado ni se han alterado evaluaciones reales.

## Propósito y límites

- Seleccionar únicamente casos **sin resolución humana aplicable** cuando ya están listos para revisión o tienen una escalada expresa.
- Clasificar la atención como `high` (incertidumbre, anomalía, potencial E2, no evaluable, discrepancias o evidencia inconsistente) y `normal` (propuesta experimental no confirmada y adquisición pendiente).
- Conservar la separación entre **detección YOLOE** y **calidad E0/E1/E2**: un resultado `ready_to_capture` no constituye clasificación; tampoco una propuesta V1/V2 consistente o con puntaje alto permite aprobación automática.
- Tratar la observación humana de forma **específica para imagen+SHA-256+momento**: una resolución anterior o aplicada a otra fotografía no cierra una incidencia nueva. Si el clasificador vuelve a generar otra instantánea posterior, puede volver a aparecer.
- La selección es una función pura. No cambia `evaluations.status`, `visual_category`, historial, metadatos, archivos ni el modelo.

## Contratos de integración

Archivo: `backend/app/review_selection.py`.

- Entradas inmutables `EvaluationFacts`, `ImageEvidence`, `DetectionEvidence`, `QualityEvidence`, `QualityView`, `UncertaintyFlag`, `HumanDecision`.
- Conversores `parse_ag037_uncertainty` para el marcador AG-037 y `parse_ag055_quality` para los `details_json` de AG-055.
- Función `select_for_human_review(facts) -> SelectionResult` devuelve elegibilidad, prioridad, motivos estructurados, IDs de imágenes y versión `ag056-review-selection-v1`.
- Motivos `RoutingReason.code` son códigos estables para traducción en UI posterior (no texto que la UI deba inferir).

### Política de cierre

AG-038 permite una decisión sobre la foto seleccionada. Para que una *instantánea concreta* deje de generar pendientes, debe existir una decisión con la misma `image_id` y el mismo hash, fechada como mínimo en el momento de esa instantánea. Una decisión sobre la primera vista **no** resuelve la segunda.

Las revisiones antiguas de AG-037 (`AG037|revision_humana|...`) no guardaron vínculo formal con una imagen. Por compatibilidad, solo pueden resolver señales **anteriores de AG-037** si la evaluación terminó como `completed`. No certifican ni resuelven una propuesta E0/E1/E2 de AG-055.

AG-055 guarda además anotaciones experimentales en archivos privados; estas no son decisiones canónicas de AG-038. El motor no las interpreta como confirmaciones oficiales. Mantener esta regla hasta diseñar una conciliación con identidad/evidencia inequívocas.

### Selección de estados

- `processing`: se excluye de la bandeja salvo incidencia explícita de detección/identidad. Un análisis experimental sobre una captura en curso no es motivo suficiente para darla por lista.
- `pending_review`: entra, aunque falte inferencia; si faltan todas las imágenes se prioriza como anomalía. No se transforma en `completed` por el motor.
- `completed`: no entra por sí solo; vuelve a entrar si hay una nueva señal sin resolver, sin alterar el estado existente.
- `error` o `cancelled`: no son tareas de revisión agronómica. Deben tratarse en el flujo de incidencia técnica o historial, **no borrarse de la base**.

### Casos que requieren atención especial en I02

1. Construir `EvaluationFacts` desde SQLite con consultas agrupadas, sin N+1; leer `reviews` y `review_decision_evidence` de forma transaccional.
2. Comprobar el SHA actual de cada foto protegida; un hash faltante o discrepante no puede tratarse como resolución válida. Optimizar caché de hashes por versión/identidad solo si existe fuente persistida confiable.
3. Parsear `details_json` sin aceptar datos defectuosos como éxito; bloquear o priorizar registros corruptos.
4. Distinguir la bandeja de pendientes del historial total: nunca eliminar filas/bitácoras para ocultar trabajo ya resuelto.
5. Evitar el cierre prematuro: las rutas actuales de revisión pueden cambiar `Evaluation.status` a `completed` después de una sola acción, pero la cola debe considerar **todas** las señales pendientes.
6. Mantener concurrencia/idempotencia que ya ofrece AG-038 y confirmar el contrato de estados al implementar la API.
7. No convertir esto en una autorización de aprobación automática; AG-055 aún no acredita calibración ni evaluación externa.

## Pruebas verificadas de I01

`backend/tests/test_ag056_review_selection.py`: **35/35 aprobadas** usando Python 3.13 y `unittest`, sin servicios, modelos o hardware. Comprueban fechas SQLite naive UTC, normalización de datos AG-037/055, decisiones obsoletas, casos multivista, hechos persistidos inconsistentes, captura en proceso, prioridad y salida determinista.

Desde la raíz del repositorio en Windows:

```powershell
$env:PYTHONPATH = "$PWD\backend"
py -3.13 -m unittest discover -s backend/tests -p "test_ag056_*.py" -v
```

La suite completa de backend/frontend y navegador **no fue ejecutada** en este entorno; este incremento no modifica ninguna ruta de API ni ningún componente de UI. No se reclama aceptación funcional E2E ni validación física.

## Siguiente incremento

I02: adaptador de lectura ORM + endpoint paginado de revisión (`GET /api/reviews/queue`) con control de acceso revisor/administrador, filtros y pruebas en SQLite aislado. Después I03 presentará la bandeja React.
