# AG-056 — Incremento 03: bandeja de revisión humana en React

## Alcance implementado

- Nueva ruta `/revisiones`, accesible en la navegación de roles `revisor` y `administrador` y protegida también en la página y en FastAPI (`require_reviewer`). No se muestra en menú `operador`.
- Consulta autenticada `GET /api/reviews/queue` mediante el cliente central: filtros `lot`, `product`, `priority`, `limit`, `offset`. Validación del esquema del servidor; errores 401/403, desconexión, datos inválidos y estado vacío.
- Orden determinado exclusivamente por el backend, con contadores obtenidos del servidor, 12 elementos por página y botones Anterior/Siguiente. Los conteos `high`, `normal` y `all` no se inventan ni se derivan de una única página.
- Caso desplegable con fotografías originales obtenidas con Bearer JWT en cabecera y URLs blob revocadas al desmontar. Vista de propuestas experimentales AG-055 **en modo solo lectura**, sin el formulario paralelo de anotaciones AG-055, y formulario AG-038 reutilizado (`ReviewDecisionPanel`), que ya gestiona UUID de idempotencia, `expectedReviewId`, validación del motivo y conflictos 409.
- Enlace a trazabilidad del expediente. La decisión guardada activa la actualización de expediente y cola; si queda otra fotografía pendiente, el servidor seguirá enviándola.
- No cambia reglas de selección, base SQLite, modelos, fotografías ni autoaprueba E0/E1/E2. No se crean tablas, migraciones, estados paralelos ni credenciales almacenadas en el navegador.

## Precauciones y limitaciones

1. La API AG-038 actual marca `completed` al registrar una decisión. Esto NO significa que todas las vistas estén resueltas; AG-056 mantiene casos en la cola mientras persistan señales pendientes. El cierre coordinado y su verificación E2E se realizará en el Incremento 04.
2. Cuando una evaluación sigue en `processing`, AG-038 no acepta escrituras. La bandeja indica que debe completarse la captura o examinarse la evidencia. Las prioridades por integridad son alertas, no autorizan clasificar sin fotografía válida.
3. El modelo AG-055 no está validado para aprobación automática ni sus puntuaciones están calibradas. Una propuesta E2 es solo una señal experimental para atención prioritaria.
4. La fecha se representa usando la zona horaria del navegador; la API conserva la fecha original en ISO 8601.
5. `GET /api/reviews/queue` calcula SHA-256 de fotografías para todas las candidatas al filtrar y contar; revisar rendimiento con conjuntos grandes.
6. `ReviewDecisionPanel` permite elegir cualquier imagen del expediente, no solo las pendientes. El listado resalta los IDs pendientes; para impedir selecciones incorrectas por UI puede incorporarse un selector especializado después de validar el flujo extremo a extremo.

## Validación local en la rama existente

```powershell
cd frontend
npm run build
npm run lint
npm test
cd ..
$env:PYTHONPATH = "$PWD\backend"
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p "test_ag056_*.py" -v
```

Pruebas manuales con FastAPI y frontend:

1. Iniciar sesión con `revisor`, abrir `/revisiones`, aplicar filtros y verificar paginación.
2. Abrir un expediente con varias imágenes y una propuesta AG-055; comprobar que la fotografía requiere autenticación.
3. Registrar una decisión de una sola fotografía mediante AG-038 y actualizar: la segunda foto debe continuar visible si tiene señales pendientes.
4. Revisar con `administrador` y confirmar consulta; con `operador` intentar `/revisiones` y la API directa y verificar bloqueo.
5. Forzar la caída de FastAPI y verificar error recuperable; cerrar y reabrir la vista para comprobar los estados desde SQLite.
6. Probar dos revisores sobre la misma revisión: verificar conflicto 409/recarga antes de guardar otra decisión.

Registrar evidencias reales (capturas, logs, pruebas) en Jira; no atribuir validación experimental a los modelos AG-055.
