# AG-046 / AGROP-54 — Incremento 04: protocolo de reinicio

**Estado inicial:** implementado, **pendiente de ejecución** en el repositorio del equipo.
**Referencia metodológica:** controles `RST-01` a `RST-04` del checklist I01.
**Corte de diseño:** 16/11/2026. No inventar resultados ni marcar el incremento como aprobado antes de revisar los logs.

## Objetivo y alcance

Verificar persistencia cuando **tres procesos independientes** de Uvicorn acceden, uno tras otro, a **la misma base de prueba y las mismas fotografías sintéticas**. Los dos cambios de proceso representan: (1) apagado ordenado y (2) terminación forzada **después de que una API respondió 2xx**. Se valida que no se pierdan registros ya confirmados.

No reinicia la aplicación productiva; no toca `backend/data/agroscan.db`, ni imágenes reales, ni servicios remotos, ni cámaras, ni ESP32. No pretende verificar consistencia ante interrupción a mitad de transacción.

## Arquitectura de aislamiento

- `backend/audit/ag046_i04_run.py` crea `tempfile.TemporaryDirectory(prefix="ag046-i04-")` fuera del repositorio y un marcador de sandbox. El directorio `data/` se crea vacío.
- `backend/audit/ag046_i04_host.py` **exige** una ruta temporal autorizada, solo escucha en `127.0.0.1` con puerto efímero y cambia `app.database.DATA_DIR`, `engine` y `SessionLocal` **antes de importar routers**. El backend productivo **no recibe** endpoints de auditoría.
- Las contraseñas, JWT y nonce de apagado se generan para cada corrida y solo se transmiten al proceso secundario mediante variables de entorno. No se imprimen ni se guardan en los informes.
- Una ruta de apagado **exclusiva del host de auditoría**, con nonce, solicita `uvicorn.Server.should_exit`; la tercera parada es también controlada. La segunda es forzada mediante `Popen.kill()`.
- Las fotos son PNG de 4×4 generados localmente. Los usuarios `operador` y `revisor`, los lotes, las piezas y las mediciones son datos de prueba.
- Un único proceso/worker escucha cada vez. Si el despliegue real usa múltiples workers, este incremento **no acredita** la sincronización entre ellos (BKP-05 requiere revisión específica).

## Secuencia de ejecución

1. **Proceso 1:** comprobar `/api/health`; autenticar operador/revisor; crear lote, evaluación y medición por API; registrar dos decisiones humanas sobre dos vistas originales; guardar snapshot de respuestas API, contenido y SHA-256 de las fotos, filas SQLite y reporte CSV.
2. **Apagado controlado:** solicitar salida del servidor; verificar que terminó y que `/api/health` no responde.
3. **Proceso 2:** iniciar una nueva instancia sobre exactamente el mismo SQLite; volver a autenticar; comparar **igualdad exacta** de la evidencia API y SQL, incluyendo FKs, decisiones, autor, estado, IDs, rutas, bytes y SHA. Registrar una nueva evaluación confirmada y reintentar la misma medición IoT para comprobar idempotencia.
4. **Parada forzada:** terminar el proceso 2 tras haber recibido éxito de la nueva escritura.
5. **Proceso 3:** iniciar otra instancia, volver a autenticar y confirmar que sobreviven la línea base y los nuevos datos. Comprobar `PRAGMA integrity_check`, `PRAGMA foreign_key_check` y hashes. Apagar ordenadamente.
6. Emitir por corrida `AG046_I04_RESUMEN.md`, `AG046_I04_RESULTADOS.json`, `AG046_I04_MATRIZ_RESULTADOS.csv` y tres archivos Uvicorn. **Con `log_level=warning` y `access_log=False`, esos archivos pueden estar vacíos; los datos de reinicio se acreditan mediante JSON, checkpoints, hashes y matriz, no por logs vacíos.**

## Criterios de aceptación

| ID | Prueba | Evidencia exigida |
|---|---|---|
| RST-01 | Persistencia de lotes, piezas, evaluaciones, mediciones | Mismo ID y contenido SQLite/API entre procesos, integridad `ok` y cero FKs huérfanas |
| RST-02 | Persistencia de fotografías | Misma cantidad, rutas, bytes HTTP y SHA-256 antes/después |
| RST-03 | Decisiones y trazabilidad | Mismo historial, autores, contenidos, secuencia y SHA-256 del CSV canónico |
| RST-04 | Reinicio real aislado | Tres arranques con `/api/health`, dos paradas controladas y una forzada; servicio detenido entre ellas |

El resultado global será `REINICIO_REAL_AISLADO_APROBADO` **únicamente** cuando los cuatro controles estén aprobados. Un fallo, arranque bloqueado, error de acceso o limpieza incompleta no debe registrarse como éxito.

## Limitaciones y evidencia adicional de campo

- No realiza una prueba física del hardware ni un ensayo de despliegue en Render/Vercel.
- No demuestra recuperación ante un corte de electricidad o `kill()` **durante** una transacción sin confirmar.
- No audita la integridad de la base operativa ni de fotos de campo.
- No es prueba de disponibilidad del frontend; SEC-04 requiere todavía validación de navegador.
- Para el informe final, complementar si se realiza una demostración con capturas reales de la UI, PID/health, antes y después, identificando entorno y fecha. No presentar capturas sintéticas como pruebas de campo.
- Conservar los JSON/logs y asociarlos a AGROP-54; evitar incluir contraseñas o JWT en capturas.

## Requisitos y uso

Desde la **raíz** del checkout local, con `.venv` backend y dependencias ya instaladas:

```powershell
.\backend\.venv\Scripts\python.exe .\backend\audit\ag046_i04_run.py
```

Leer el resumen de la carpeta más reciente `docs/ag046/runs/AG046_I04_*`. No hacer `git add .` ni modificar carpetas de datos reales para esta prueba.
