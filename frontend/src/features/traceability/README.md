# Contrato provisional de trazabilidad

El frontend todavía **no está conectado** a la API. `traceabilityService.getByEvaluationId()` devuelve un error explícito de indisponibilidad, nunca registros ficticios.

Pendiente de acordar con Backend (Josmely):

- Ruta y autorización para consultar una evaluación individual, vinculada a lote y pieza.
- Recuperación de identificadores y metadatos de evidencias RGB sin exponer archivos de forma insegura.
- Conservación del resultado original, versiones de calibración/modelo/reglas y registro inmutable de revisiones.
- Revisión autorizada con autor, fecha, motivo, valor anterior y valor nuevo, sin reemplazar el original.
- Distinción entre **no encontrado** (404), **sin autorización** (401/403), errores y servicio no conectado.
- Semántica de estados como pendiente de revisión, completado, anulado, y su relación con la clasificación visual.

`TraceabilityRecord` es un **modelo provisional de la interfaz**. No se debe asumir que la estructura coincide con el backend hasta acordar el contrato.

## Pruebas

```sh
npm test
```

Se ejecutan pruebas del servicio desconectado, validación de referencias y orden/inmutabilidad de la cronología (con fixtures de prueba, nunca registros operativos).
