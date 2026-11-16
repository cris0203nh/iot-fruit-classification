# AG-046 / Incremento 03 — Corrección R2 de BKP-05 (compatible con rama Vercel)

**Origen:** ejecución local del 16/11/2026, Git HEAD `42316b947fd4ce71e80b3832e70bd299ccd99d25` (declarado en el informe del usuario).

**Hallazgo confirmado antes del cambio:** la prueba estricta `test_bkp05_alta_lote_debe_bloquearse_durante_restauracion` observó HTTP 201 en `POST /api/lots` mientras `suspend_capture()` estaba activo. El ejecutor lo identificó como `BRECHA_BKP05_CONFIRMADA`.

## Causa técnica

La suspensión era un estado en memoria compartido por algunas dependencias `capture_guard`, pero no todas las rutas de escritura de la API usaban dicha dependencia. El alta de lotes no estaba incluida.

## Corrección implementada (pendiente de ejecutar localmente)

- Se agrega un guard HTTP central a todas las operaciones **POST, PUT, PATCH y DELETE** bajo `/api/`, con protección durante toda la ejecución de la solicitud.
- Se exceptúan exclusivamente las rutas de creación y restauración de respaldos (`/api/admin/backups` y `/api/admin/backups/restore`) para que puedan adquirir `suspend_capture()` sin bloquearse a sí mismas.
- Se devuelve HTTP 503 con `CAPTURE_SUSPENDED` al intentar una escritura mientras la suspensión está activa.
- La prueba estricta ahora verifica cinco rutas de escritura (`lotes`, `evaluaciones`, `mediciones IoT`, `usuarios`, `decisiones humanas`) y confirma que el lote de prueba no fue creado.
- Se ajusta la identificación automática del hallazgo para reconocer una o más fallas de HTTP distinto de 503; nunca se convierte una prueba fallida en aprobada.

## Limitaciones y criterios de aceptación

1. **El cambio protege únicamente un proceso FastAPI:** el estado de `capture_control` es un objeto Python en memoria. Ejecutar varios workers/procesos o instancias independientes no comparte la suspensión. No declarar BKP-05 aprobado en despliegues multiproceso sin implementar una exclusión compartida y ensayarla.
2. Las operaciones GET pueden continuar durante la restauración. No se acredita aquí una vista de lectura consistente frente a la sustitución de SQLite y las imágenes; requiere una prueba adicional o política explícita.
3. El guard no protege escrituras de procesos externos a FastAPI (puente serie o tareas programadas que escriban directamente SQLite o el sistema de archivos). Verificar arquitectura real de despliegue.
4. No se cambian modelos, migraciones, contratos de payload, respuestas 401/403 normales ni reglas de negocio.
5. Reejecutar `backend/audit/ag046_i03_run.py` y conservar logs. Todos los pasos deben informar **APROBADO** para declarar aprobada la batería automatizada aislada. Si `i03_integridad` sigue fallando, revisar su log; el problema es distinto del hallazgo BKP-05.

**Estado de esta nota:** cambio preparado, **sin resultado de ejecución local**. La evidencia anterior de la brecha se conserva en `docs/ag046/runs/AG046_I03_20261116T133838_153430Z/`.
