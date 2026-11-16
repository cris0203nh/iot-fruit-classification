# AG-046 — Trazabilidad de correcciones e incidencias (I01-I04)

Registro preparado para el cierre I05. Los estados de **ejecución** derivan de las salidas locales aportadas por el responsable (16/11/2026). El consolidador I05 confirmará las fuentes y sus hashes al ejecutarse en ese repositorio.

| Hallazgo | Observación inicial | Corrección | Evidencia posterior informada | Estado técnico |
|---|---|---|---|---|
| H01 / SEC-11 | Ruta IoT acepta medición sin credencial | Ninguna, requiere diseño de autenticación | Prueba de caracterización I02 aprobada; riesgo permanece | ABIERTO |
| H02 / BKP-05 | `POST /api/lots` fue aceptado durante suspensión | Guard HTTP global de escrituras API, excepto rutas de respaldo | I03 `bkp05_prueba_estricta: APROBADO` | VERIFICADO EN UN PROCESO; MULTIPROCESO PENDIENTE |
| H03 / SEC-12 | Dos flujos humanos tienen permisos distintos | Ninguna: es decisión funcional | I02 caracteriza la separación, sin validarla funcionalmente | PENDIENTE |
| H04 / BUG-001 | README declara sin login/migraciones/backup | README actualizado en I05 | Verificación estática por consolidador (pendiente local) | CORREGIDO, PENDIENTE CONCILIACIÓN |
| H05 / RST | Sin prueba real de detener Uvicorn | Ejecutor I04 con sandbox aislado | `RST-01`–`RST-04: APROBADO` | CERRADO CON ALCANCE AISLADO |
| H06 / INT-08 | No todas las imágenes históricas tienen hash original | Ninguna: requiere política de procedencia | I03 valida únicamente hash ya registrado | LIMITACIÓN ABIERTA |
| OBS-I02-1 | HTTPX no acepta cabecera con `inválido` no ASCII | Token malformado en formato ASCII | I02 14/14 | CORREGIDO EN TEST |
| OBS-I02-2 | Revisiones antiguas esperaban éxito sin fotos | Fixture actualizado; rechazo 409 sin evidencia añadido | Regresión roles 24/24 | CORREGIDO EN TEST |
| OBS-I02-3 | Ejecutor no contó correctamente Node | Formato TAP + recuento explícito | Frontend 4/4 | CORREGIDO EN EJECUTOR |
| OBS-I03-1 | SQLite temporal abierto en Windows | `contextlib.closing` en tests | I03 integridad 16/16 | CORREGIDO EN TEST |
| OBS-I04-1 | Sandbox válido rechazado por comparación de rutas | Validación compatible con Windows y marcador temporal | I04 4/4 | CORREGIDO EN EJECUTOR |
| OBS-I04-2 | Apagado temporal devolvía HTTP 422 por anotación `Request` | Importación de `Request` a nivel de módulo | I04 4/4 | CORREGIDO EN EJECUTOR |

No marcar los riesgos H01, H03 o H06 como eliminados por el éxito de las pruebas automatizadas. Ninguna corrección de I05 cambia políticas de negocio ni modifica datos operativos.
