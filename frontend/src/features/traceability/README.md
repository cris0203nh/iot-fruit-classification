# Integración de trazabilidad — contrato vigente

La consulta de trazabilidad está conectada con `GET /api/evaluations/{id}/traceability` de FastAPI.

- Los identificadores publicados por el backend tienen el formato `E-000001` (hasta nueve dígitos).
- `GET /api/evaluations` y `GET /api/evaluations/{id}` alimentan Historial y Detalle.
- La cronología comienza por el resultado original y añade revisiones ordenadas por fecha, sin modificar los datos recibidos.
- Las imágenes usan exclusivamente rutas locales comprobadas `/api/images/I-{id}`, servidas por FastAPI.
- La UI diferencia 404 (no encontrado), 401/403 (denegado), caída de FastAPI y respuesta JSON inesperada.
- No se han habilitado acciones de modificación, anulación o revisión. El backend actual acepta `actorId` de entrada pero aún no autentica identidades; **no exponerlo a redes públicas**.
- Una evaluación en `processing` puede no contener peso, categoría visual, imágenes ni revisiones. No se inventan datos.

Ejecutar `npm test`, `npm run lint` y `npm run build` desde `frontend/` antes del PR.
