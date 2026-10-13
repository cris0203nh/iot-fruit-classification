# Contrato de la API - AgroScan

Todo cambio de campos requiere acuerdo entre Backend, Frontend (y IoT si afecta al sensor) mediante Pull Request.

## Convenciones

- Fechas ISO-8601 en UTC; el frontend las convierte a hora local.
- Errores: `{"detail": "mensaje"}`. 404 no existe, 409 conflicto o duplicado, 422 datos inválidos.
- Producto: `mango` | `tomate`.
- Estado: `processing` | `completed` | `pending_review` | `error` | `cancelled`.
- Peso en gramos.

## Lotes

`POST /api/lots`: `{"code": "LOTE-001", "product": "mango", "responsible": ""}`

`code`: 2 a 32 caracteres (letras, números, guion o guion bajo; inicia con letra o número). Respuestas: 201, 409 si existe, 422 si es inválido.

Respuesta: `{"id": 1, "code": "LOTE-001", "product": "mango", "status": "open", "responsible": "", "created_at": "..."}`

## Evaluaciones

`POST /api/evaluations`: `{"lotId": "LOTE-001", "pieceId": "P-001"}`. `lotId` es la referencia del lote. Respuestas: 201, 404 (lote inexistente), 409 (lote cerrado), 422.

Detalle (id con forma `E-000001`):

```json
{"id": "E-000001", "lotId": "LOTE-001", "pieceId": "P-001", "product": "mango",
 "registeredAt": "...", "status": "processing", "weightGrams": null, "imageCount": 0,
 "evidence": [], "visualCategory": null, "reviewNote": null, "failureReason": null}
```

`GET /api/evaluations` devuelve la lista resumida; filtros `?lot=`, `?product=`, `?status=`.

`visualCategory` es siempre el valor original; el vigente es el `updatedValue` de la última revisión.

## Sincronización de peso

Flujo: crear evaluación, `weight/pre`, captura de imagen (pendiente), `weight/post`.

- `weight/pre`: lectura estable, recibida después de crear la evaluación y con menos de 10 s.
- `weight/post`: otra lectura estable posterior, mismo `device_id` y `boot_id`, diferencia máxima de 5 g.
- Respuesta: `{"stage": "pre", "weightG": 152.8, "deviceId": "station-001", "receivedAt": "..."}`.
- 409 si falta la lectura (reintentar) o si hay un fallo. En fallo (sensor reiniciado, peso cambiado, 180 s agotados) la evaluación pasa a `error` y `failureReason` guarda el motivo.

## Revisiones y trazabilidad

`POST /api/evaluations/{id}/reviews`: `{"actorId": "josmely", "reason": "...", "newValue": "observado"}`. Solo en estado `completed` o `pending_review`; si no, 409.

`POST /api/evaluations/{id}/cancel`: `{"actorId": "josmely", "reason": "..."}`. 409 si ya está anulada.

`GET /api/evaluations/{id}/traceability` devuelve `{evaluation, calibrationReference, modelVersion, rulesVersion, reviews[]}`. Cada review: `{id, performedAt, actorId, type: "review" | "cancellation", reason, previousValue, updatedValue}`. Nunca se sobrescribe el original.

## IoT (ESP32)

`POST /api/iot/measurements`:

```json
{"schema_version": 1, "device_id": "station-001", "boot_id": "boot-a1", "seq": 1,
 "weight_g": 152.8, "stable": true, "calibration_version": "cal-001"}
```

- `weight_g` entre 0 y 5000; si no, 422 (no reintentar).
- 200: `{"received": true, "duplicate": false, "receivedAt": "..."}`.
- Misma combinación `device_id` + `boot_id` + `seq` = duplicado, no se guarda ni refresca la hora.
- Fallo de red o 5xx: reintento limitado con la misma `seq`.

`GET /api/iot/status`: `{"online": true, "deviceId": "...", "weightG": 152.8, "stable": true, "receivedAt": "...", "ageSeconds": 2.1}`. La lectura es vigente 10 s; después `online` es `false` y `weightG` y `stable` son `null`.