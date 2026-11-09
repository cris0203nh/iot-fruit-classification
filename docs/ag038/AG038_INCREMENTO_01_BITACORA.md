# AgroScan — AG-038 / AGROP-46 — Incremento 01: decisiones y bitácora

## Criterio de aceptación

> «Bitácora conserva valor original, nuevo valor, autor, fecha y motivo; nunca sobreescribe evidencia».

Este incremento agrega una **operación explícita y auditable** de decisión humana, distinta de la compuerta de detección de AG-037. Reutiliza la tabla `reviews` como bitácora principal: cada decisión genera una fila `Review(type=review)` y una fila **uno a uno** de `review_decision_evidence`, que contiene la acción, imagen inspeccionada, SHA256 y UUID de solicitud. La nueva tabla **no duplica** los datos de la bitácora.

## Flujo y decisiones

- `initial_label`: asignar por **primera vez** E0/E1/E2 si no existía grado. No se presenta como corrección de YOLOE.
- `confirm`: confirmar exactamente el **valor vigente** (anterior = nuevo) sin alterarlo, dejando un evento de revisión.
- `correct`: registrar un valor **diferente** del vigente (anterior → nuevo) con motivo; nunca alterar `Evaluation.visual_category` ni registros anteriores.
- `no_evaluable`: registrar explícitamente ausencia de dictamen de calidad sin inventar E0/E1/E2.

Se permite revisar evaluaciones `pending_review` y `completed`, nunca las `processing`, `error` o `cancelled`.
Los grados **E0/E1/E2** no se convierten a categorías comerciales **primera/segunda**. Estas últimas se pueden confirmar o corregir dentro de su propia taxonomía en registros históricos.

**No confundir:** YOLOE detecta mango/tomate, no predice calidad E0/E1/E2. AG-037 mantiene sus endpoints históricos; las nuevas decisiones auditadas de AG-038 se realizan mediante el endpoint exclusivo `review-decisions`.

## API

- `GET /api/evaluations/{E-...}/review-decisions` (usuario autenticado): valor original, vigente, revisión más reciente y decisiones AG-038.
- `POST /api/evaluations/{E-...}/review-decisions` (revisor/admin): `action`, `imageId`, `newValue`, `reason`, `expectedReviewId` (revisión vista por el usuario), `requestId` (UUID v4).
- Respuesta: ID de revisión, anterior/nuevo, acción, usuario **obtenido del JWT**, fecha **del servidor**, justificación, imagen, SHA256 y UUID de solicitud.

La API rechaza valores inválidos, cambios de taxonomía, imágenes ajenas o inaccesibles, alteraciones frente a snapshots YOLOE, reintentos con el mismo UUID y otro contenido, y revisiones obsoletas. En SQLite se usa un bloqueo de escritura inmediato antes de consultar la revisión para serializar las decisiones concurrentes. La clave `(evaluation_id, request_id)` es única. Un reintento idéntico devuelve el mismo evento sin duplicarlo.

**Limitación importante:** los endpoints antiguos `/reviews` y `/vision/resolve` se mantienen por compatibilidad; sus eventos previos se conservan en la trazabilidad general pero no contienen todos los metadatos nuevos. La auditoría extendida aplica a operaciones registradas por `review-decisions`.

## React

En **Trazabilidad → Detalle** se añade el panel «AG-038 · Confirmación, corrección y bitácora». Muestra original y vigente, las decisiones previas y un formulario exclusivo para revisor/admin. Las cuentas operadoras pueden **consultar**, pero no registrar decisiones. El formulario usa el ID de revisión obtenido del servidor y conserva el mismo UUID al reintentar una solicitud cuyo resultado sea incierto.

## Migración

Revisión nueva: `b38c99a10246`; revisión anterior `c7e41a03b037`. La migración es **aditiva** y no cambia ni elimina fotografías, `vision_assessments` ni filas antiguas de `reviews`. Requiere hacer respaldo de `backend/data/agroscan.db` con FastAPI detenido antes de ejecutar `alembic upgrade head`.

## Comprobación sin ESP32

La suite `backend/tests/test_agrop46_review_decisions.py` crea SQLite temporal y utiliza eventos controlados. No prueba inferencia real ni hardware. El frontend incluye cuatro pruebas unitarias de las reglas de selección. Además de las pruebas automáticas, comprobar visualmente en React los tres casos: etiquetado inicial, confirmación y corrección, y verificar el historial después de recargar la página.

## Evidencias para Jira

Adjuntar registro de suite backend, suite frontend y build; captura del panel mostrando original, vigente, motivo, autor, hora e identificador SHA256; y comprobación de que la fotografía sigue siendo la misma. No incluir credenciales, DB real, ZIPs de fotografías privadas ni imágenes de personas ajenas. No marcar AG-038 como `Done` antes de validar en el repositorio del usuario y registrar evidencia funcional.
