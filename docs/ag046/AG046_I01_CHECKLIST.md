# AG-046 — Checklist técnico I01 (línea base)

**Fecha de corte:** 16/11/2026. **Fuente:** `main` commit `1d3b66b7017f7f9139a5a35521f458bf100f6a66`.
**Semántica obligatoria:** `Estado_auditoria_estatica` documenta observación de código/test; **`Resultado_ejecucion=PENDIENTE` para los 34 controles**. Prohibido transformar `COBERTURA_DE_TEST_EXISTENTE` en `APROBADO` sin ejecutar y conservar evidencia en el corte correspondiente.

## Cómo actualizar

En cada fila del CSV, cambiar `Resultado_ejecucion` a `APROBADO`, `FALLIDO`, `BLOQUEADO` o `NO_APLICA_JUSTIFICADO` **solo después** de realizar la prueba. Registrar en `Evidencia_real_y_observaciones`: SHA/versión, comando, fecha, entorno aislado, comportamiento obtenido y ruta del log/captura. Ante `FALLIDO`, crear/actualizar incidencia en `AG046_I01_REGISTRO_HALLAZGOS.md`.

## Checklist de ejecución pendiente

### Seguridad

- [ ] **SEC-01 — JWT requiere secreto configurado >=32 caracteres**
  - Código/test: `backend/app/security.py`. Estado estático: `OBSERVADO_EN_CODIGO`.
  - Criterio: Inicialización falla con clave corta/vacía; no filtra clave. Próximo: **I02**.
- [ ] **SEC-02 — JWT restringe HS256 y requiere sub/iat/exp**
  - Código/test: `backend/app/security.py`. Estado estático: `OBSERVADO_EN_CODIGO`.
  - Criterio: Token inválido, manipulado o expirado devuelve HTTP 401. Próximo: **I02**.
- [ ] **SEC-03 — Login verifica contraseña cifrada y estado de usuario**
  - Código/test: `backend/app/routers/auth.py;backend/app/dependencies.py`. Estado estático: `OBSERVADO_EN_CODIGO`.
  - Criterio: Credenciales inválidas o usuario inactivo rechazan acceso. Próximo: **I02**.
- [ ] **SEC-04 — Frontend no persiste JWT en localStorage ni URL**
  - Código/test: `frontend/src/services/agroscanApi.ts`. Estado estático: `OBSERVADO_EN_CODIGO`.
  - Criterio: Token reside en memoria; se limpia al salir. Próximo: **I02**.
- [ ] **SEC-05 — Rutas autenticadas rechazan petición sin token**
  - Código/test: `backend/app/dependencies.py;backend/tests/test_agrop47_permissions.py`. Estado estático: `COBERTURA_DE_TEST_EXISTENTE`.
  - Criterio: HTTP 401; no hay modificación de datos. Próximo: **I02**.
- [ ] **SEC-06 — Operador no corrige ni anula evaluación por ruta formal**
  - Código/test: `backend/app/routers/evaluations.py;backend/tests/test_agrop47_permissions.py`. Estado estático: `COBERTURA_DE_TEST_EXISTENTE`.
  - Criterio: HTTP 403; evento no creado. Próximo: **I02**.
- [ ] **SEC-07 — Revisor puede decidir pero no anular**
  - Código/test: `backend/app/routers/review_decisions.py;backend/app/routers/evaluations.py`. Estado estático: `OBSERVADO_EN_CODIGO`.
  - Criterio: Revisión autorizada; anulación HTTP 403. Próximo: **I02**.
- [ ] **SEC-08 — Administración usuarios reservada al administrador**
  - Código/test: `backend/app/routers/users.py`. Estado estático: `OBSERVADO_EN_CODIGO`.
  - Criterio: Operador/revisor HTTP 403 para alta y cambio de roles. Próximo: **I02**.
- [ ] **SEC-09 — Backup y restore reservados al administrador**
  - Código/test: `backend/app/routers/backup.py;backend/tests/test_agrop53_backup_api.py`. Estado estático: `COBERTURA_DE_TEST_EXISTENTE`.
  - Criterio: No admin HTTP 403; sin token HTTP 401. Próximo: **I02**.
- [ ] **SEC-10 — Cola de revisión requiere revisor**
  - Código/test: `backend/app/routers/review_queue.py;backend/tests/test_ag056_review_queue.py`. Estado estático: `OBSERVADO_EN_CODIGO`.
  - Criterio: Operador HTTP 403; revisor/admin HTTP 200. Próximo: **I02**.
- [ ] **SEC-11 — Autenticación de lectura IoT acorde al despliegue**
  - Código/test: `backend/app/routers/iot.py`. Estado estático: `HALLAZGO_POR_EVALUAR`.
  - Criterio: Dispositivos no autorizados no escriben lecturas al exponer API. Próximo: **I02**.
- [ ] **SEC-12 — Regla de autorización de anotación E0/E1/E2 documentada**
  - Código/test: `backend/app/routers/quality_prediction.py;backend/app/routers/review_decisions.py`. Estado estático: `DIFERENCIA_DE_ROLES`.
  - Criterio: La política aplicada coincide con el flujo funcional aprobado. Próximo: **I02**.

### Integridad

- [ ] **INT-01 — SQLite habilita claves foráneas por conexión**
  - Código/test: `backend/app/database.py`. Estado estático: `OBSERVADO_EN_CODIGO`.
  - Criterio: PRAGMA foreign_keys=1 en todas las conexiones del entorno. Próximo: **I03**.
- [ ] **INT-02 — Integridad estructural SQLite**
  - Código/test: `backend/app/services/backup_service.py`. Estado estático: `OBSERVADO_EN_CODIGO`.
  - Criterio: PRAGMA integrity_check = ok. Próximo: **I03**.
- [ ] **INT-03 — Integridad referencial SQLite**
  - Código/test: `backend/app/services/backup_service.py`. Estado estático: `OBSERVADO_EN_CODIGO`.
  - Criterio: PRAGMA foreign_key_check devuelve cero incidencias. Próximo: **I03**.
- [ ] **INT-04 — Registros de imágenes tienen archivo físico y vínculo válido**
  - Código/test: `backend/app/services/backup_service.py;backend/app/routers/images.py`. Estado estático: `OBSERVADO_EN_CODIGO`.
  - Criterio: Cada images.relative_path apunta a un archivo existente y a evaluación. Próximo: **I03**.
- [ ] **INT-05 — Carga JPG/PNG restringe formato y tamaño**
  - Código/test: `backend/app/routers/images.py`. Estado estático: `OBSERVADO_EN_CODIGO`.
  - Criterio: Rechazo 422 para vacíos, formato inválido, >5 MiB. Próximo: **I03**.
- [ ] **INT-06 — Fallo de disco no deja imagen huérfana**
  - Código/test: `backend/app/routers/images.py;backend/tests/test_agrop52_image_recovery.py`. Estado estático: `COBERTURA_DE_TEST_EXISTENTE`.
  - Criterio: Transacción y archivos coherentes tras error de escritura. Próximo: **I03**.
- [ ] **INT-07 — Carga de imagen idempotente**
  - Código/test: `backend/app/routers/images.py`. Estado estático: `OBSERVADO_EN_CODIGO`.
  - Criterio: Misma Idempotency-Key no duplica imagen. Próximo: **I03**.
- [ ] **INT-08 — SHA-256 original validado antes de decisión formal**
  - Código/test: `backend/app/routers/review_decisions.py`. Estado estático: `OBSERVADO_EN_CODIGO`.
  - Criterio: Archivo alterado no permite registrar decisión. Próximo: **I03**.
- [ ] **INT-09 — Dos fotografías por evaluación respetan cierre de revisión**
  - Código/test: `backend/app/review_completion.py;backend/tests/test_ag056_final_api.py`. Estado estático: `COBERTURA_DE_TEST_EXISTENTE`.
  - Criterio: No cierra hasta resolver todas las evidencias requeridas. Próximo: **I03**.
- [ ] **INT-10 — Reporte por lote entrega hash de CSV reproducible**
  - Código/test: `backend/app/routers/piece_history_report.py`. Estado estático: `OBSERVADO_EN_CODIGO`.
  - Criterio: CSV idéntico genera mismo SHA-256. Próximo: **I03**.

### Respaldo

- [ ] **BKP-01 — Respaldo incorpora SQLite e imágenes declaradas**
  - Código/test: `backend/app/services/backup_service.py;backend/tests/test_agrop53_backup_integration.py`. Estado estático: `COBERTURA_DE_TEST_EXISTENTE`.
  - Criterio: ZIP contiene SQLite, payload e inventario manifest. Próximo: **I03**.
- [ ] **BKP-02 — Validar SHA-256 y rutas ZIP seguras**
  - Código/test: `backend/app/services/backup_service.py;backend/tests/test_agrop53_backup.py`. Estado estático: `COBERTURA_DE_TEST_EXISTENTE`.
  - Criterio: ZIP alterado o traversal se rechaza sin modificar origen. Próximo: **I03**.
- [ ] **BKP-03 — Restauración conserva lotes, piezas, revisiones e imágenes**
  - Código/test: `backend/tests/test_agrop53_backup_integration.py`. Estado estático: `COBERTURA_DE_TEST_EXISTENTE`.
  - Criterio: Identificadores/relaciones/bytes idénticos a respaldo. Próximo: **I03**.
- [ ] **BKP-04 — Rollback preserva información si falla restauración**
  - Código/test: `backend/app/services/backup_service.py`. Estado estático: `OBSERVADO_EN_CODIGO`.
  - Criterio: No queda operación parcial ni pérdida de datos. Próximo: **I03**.
- [ ] **BKP-05 — Restauración no compite con otras escrituras**
  - Código/test: `backend/app/services/capture_control.py;backend/app/routers/backup.py`. Estado estático: `HALLAZGO_POR_EVALUAR`.
  - Criterio: Operaciones activas no corrompen o pierden cambios. Próximo: **I03**.

### Reinicio

- [ ] **RST-01 — Datos de lote y evaluación persisten tras reinicio real**
  - Código/test: `backend/app/database.py`. Estado estático: `SIN_EVIDENCIA_DE_EJECUCION`.
  - Criterio: Mismos IDs/estados y respuestas API antes/después. Próximo: **I04**.
- [ ] **RST-02 — Imágenes persisten byte a byte y se sirven tras reinicio**
  - Código/test: `backend/app/routers/images.py`. Estado estático: `SIN_EVIDENCIA_DE_EJECUCION`.
  - Criterio: SHA-256 y número de archivos sin variación. Próximo: **I04**.
- [ ] **RST-03 — Decisiones y bitácora permanecen inmutables**
  - Código/test: `backend/app/routers/review_decisions.py`. Estado estático: `SIN_EVIDENCIA_DE_EJECUCION`.
  - Criterio: Misma secuencia, autor y contenido antes/después. Próximo: **I04**.
- [ ] **RST-04 — Reinicio con servidor detenido y datos aislados**
  - Código/test: `backend/app/main.py`. Estado estático: `SIN_EVIDENCIA_DE_EJECUCION`.
  - Criterio: Cierre controlado, nueva ejecución, health y consulta correcta. Próximo: **I04**.

### Mantenimiento

- [ ] **MNT-01 — README explica login, Alembic, respaldo y límites**
  - Código/test: `backend/README.md;backend/app/security.py;backend/alembic/`. Estado estático: `DEFECTO_DOCUMENTAL_CONFIRMADO`.
  - Criterio: README corresponde a código actual, sin instrucciones de borrar BD real. Próximo: **I05**.
- [ ] **MNT-02 — Evidencias de cada control conservadas sin secretos**
  - Código/test: `docs/ag046/`. Estado estático: `DOCUMENTACION_CREADA`.
  - Criterio: Logs, capturas, versión, fecha y criterios de aceptación. Próximo: **I02-I05**.
- [ ] **MNT-03 — Todos los defectos tienen estado y severidad**
  - Código/test: `docs/ag046/AG046_I01_REGISTRO_HALLAZGOS.md`. Estado estático: `DOCUMENTACION_CREADA`.
  - Criterio: Reproducción, corrección/aceptación y verificación trazables. Próximo: **I02-I05**.

## Interpretación al terminar I01

- Checklist generado: **34 controles identificados**.
- Pruebas ejecutadas dentro de I01: **0** (auditoría estática de código, no tests).
- Controles aprobados en ejecución: **0**, porque todavía no se ha ejecutado ninguna verificación para esta actividad.
- Observaciones iniciales registradas: **6**; no todas son bugs confirmados.
- Progreso AG-046: **solo planificación técnica y trazabilidad inicial**, no aceptación de seguridad/integridad/reinicio.

## Evidencia mínima para los próximos incrementos

| Incremento | Evidencia válida | Restricción |
|---|---|---|
| I02 | Respuestas HTTP 401/403/200/201 y tests de rol/token, con identidades sintéticas | Nunca copiar JWT o contraseñas en Git |
| I03 | Integridad SQLite, conteo de archivos/relaciones, SHA-256, ZIP y rollback | Solo BD y archivos aislados; nunca restaurar sobre datos reales |
| I04 | PID/proceso previo y nuevo, respuestas antes/después, hashes, capturas del navegador | Probar parada y arranque reales, no solo recrear `TestClient` |
| I05 | Resultado de regresiones, bugs cerrados/aceptados, README actualizado, enlace a PR | No marcar `Done` con hallazgos altos/críticos sin resolver o aceptar |
