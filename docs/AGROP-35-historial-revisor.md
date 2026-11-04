# AGROP-35 [AG-027] — Consulta de historial por lote y pieza

## Objetivo

El revisor consulta evaluaciones guardadas en SQLite, filtrando por lote y pieza, y recupera peso, fecha, estado e imágenes asociadas. Se extiende el historial existente sin crear nuevos endpoints ni alterar datos.

## Implementación

- Los roles `revisor`, `operador` y `administrador` pueden iniciar sesión. El revisor se dirige al Historial y solo recibe navegación de consulta; las rutas de creación de evaluación, lotes y mantenimiento no le presentan controles de escritura. El backend conserva la autorización definitiva.
- Los filtros independientes de lote y pieza se combinan con búsqueda general, producto y estado. Se muestra la cantidad real de fotografías por evaluación.
- El detalle muestra la fecha, el estado, el peso si existe y las imágenes protegidas mediante cabecera Bearer. «No disponible» no es un peso ficticio.
- El token sigue únicamente en memoria. Después de recargar o reiniciar se requiere un nuevo inicio de sesión.

## Evidencia para Jira (capturas reales)

1. Sesión de **revisor** y lista de historial con filtros por lote y pieza (por ejemplo, `E-000010`, lote `TEST-MANGO-20261013-01`, pieza `PEE_01`).
2. Detalle de la misma evaluación mostrando fecha, estado, peso `No disponible` si corresponde y fotografía original con ID.
3. Reiniciar FastAPI, actualizar la página, volver a iniciar sesión y recuperar **el mismo ID** y su evidencia desde SQLite; registrar antes/después de la operación. Los tests de solicitud repetida no reemplazan esta demostración real.

## Pruebas automatizadas

```powershell
cd frontend
npm test
npm run lint
npm run build
```

No presentar como validado un pesaje físico ni una prueba de reinicio hasta ejecutarlos. No adjuntar tokens, contraseñas ni archivos `.env`/`.db`.
