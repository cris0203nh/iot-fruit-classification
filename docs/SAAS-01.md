# SaaS-01 — preparación multiempresa (2026-11-16)

Resultado: sistema de una sola empresa; no apto para compartir una instancia entre empresas todavía. Sin cambios de producción, esquema, endpoints, YOLO, SVC ni firmware.

## Superficie que requiere aislamiento

Rutas relativas a `backend/app/`; los endpoints conservan su contrato actual.

| Área | Tablas | Endpoints y archivos afectados |
| --- | --- | --- |
| Lotes/piezas | `lots`, `pieces` | `/api/lots`, `/api/lots/{lot_id}`; `models.py`, `routers/lots.py`, búsquedas por código en evaluaciones/historial |
| Evaluaciones | `evaluations`, `vision_prechecks` | `/api/evaluations` y todas sus subrutas; `/api/vision/precheck`, `/api/evaluations/auto`; `routers/evaluations.py`, `routers/auto_registration.py`, `auto_registration_models.py` |
| Evidencia y resultados persistidos | `images`, `vision_assessments`, `fruit_geometries`, `ag054_planar_calibrations`, `ag054_board_calibrations`, `ag054_dimensional_comparisons`, `ag055_quality_predictions` | `/api/images/{image_id}`, `/api/evaluations/{id}/images`, subrutas `/vision/*`; `routers/images.py`, `uncertainty.py`, `fruit_geometry.py`, `planar_calibration.py`, `board_calibration.py`, `quality_prediction.py` y sus `*_models.py`; archivos `DATA_DIR/images` |
| IoT | `measurements`, referencias desde `evaluations` | `/api/iot/measurements`, `/api/iot/status`, `/api/evaluations/{id}/weight/*`; `routers/iot.py`, `routers/evaluations.py`, `iot_schemas.py` |
| Revisiones | `reviews`, `review_decision_evidence` | `/api/reviews/queue`, `/api/evaluations/{id}/reviews`, `/cancel`, `/review-decisions`, resolución y revisiones de calidad; `routers/review_queue.py`, `review_queue.py`, `routers/review_decisions.py`, `decision_models.py` y routers de evaluaciones/calidad/incertidumbre |
| Historial/reportes | Derivados de las tablas anteriores | `/api/piece-history`, `/{lot_code}/{piece_code}`, `/report`; `/api/evaluations/vision/board-validation/report`; `routers/piece_history*.py`, `routers/board_calibration.py` |
| Identidad/permisos | `users`, `user_roles`, `roles` | `/api/auth/*`, `/api/users*`; `security.py`, `dependencies.py`, `routers/auth.py`, `routers/users.py`, `bootstrap_admin.py`; definir membresías por empresa, catálogo de roles puede seguir compartido |
| Respaldos | Toda la BD, incluida identidad y `alembic_version`, más imágenes | `/api/admin/backups`, `/restore`; `routers/backup.py`, `services/backup_service.py`, `services/capture_control.py`, `main.py`, `DATA_DIR/backups` |

Frontend relacionado: `frontend/src/services/agroscanApi.ts`, `features/auth/AuthGate.tsx`, `features/history/historyService.ts`, `features/traceability/traceabilityService.ts`. Sus filtros no son una barrera de seguridad; el aislamiento debe imponerse en backend, incluyendo consultas por ID, códigos, relaciones, agregados e idempotencia.

## Riesgos prioritarios

- **Crítico:** roles globales y consultas sin empresa permiten acceso global a cualquier usuario con rol permitido. Las FK actuales no impiden relaciones entre empresas futuras. Revisar unicidad global de `lots.code`, `users.username` y `(device_id, boot_id, seq)`; conservar las claves por lote/evaluación/imagen donde corresponda.
- **Crítico:** POST de mediciones y GET de estado IoT no exigen autenticación. `latest_ready()` toma la última medición global: permite inyección de lecturas y mezcla entre dispositivos. Requiere identidad de dispositivo y asociación autorizada a empresa/evaluación antes de exposición compartida.
- **Alto:** respaldo/restauración reemplazan todas las empresas y usuarios. Bloqueo en memoria protege solo un proceso; lectores, procesos externos y conexiones activas no quedan coordinados. Restauración no gestiona explícitamente archivos WAL/SHM. No habilitar varios workers con esta garantía.
- **Alto:** JWT contiene solo ID de usuario y fechas; no hay revocación de sesión ni límite de intentos de login en la aplicación. Restaurar usuarios/roles antiguos puede reactivar accesos con tokens aún válidos. No aceptar empresa del cliente sin validar membresía vigente.
- Protecciones verificadas: Argon2, HS256 restringido, claims obligatorios, expiración, usuario activo y roles consultados en cada solicitud; token frontend en memoria. SHA-256 comprueba integridad del respaldo, no su procedencia. El ZIP incluye hashes de contraseñas y datos de toda la instancia.

## Dependencias de SQLite

- `database.py`: URL fija, `check_same_thread=False`, evento `PRAGMA foreign_keys=ON`. `AGROSCAN_DATABASE_URL` se respeta en Alembic, **no** en el motor de la aplicación: riesgo de migrar otra BD.
- `services/backup_service.py`: `sqlite3`, API `backup()`, PRAGMA de integridad/FK, sustitución física de `agroscan.db`.
- `routers/review_decisions.py`: `BEGIN IMMEDIATE` serializa revisiones solo en SQLite; otro motor necesitaría una garantía equivalente.
- `auto_registration_models.py` y `routers/auto_registration.py`: contador de reclamaciones y asignación de códigos dependen del bloqueo de escritura SQLite; reevaluar junto con `with_for_update()`.
- `alembic/env.py`: PRAGMA FK OFF/ON y reconstrucción por lotes; migración `7ccb39e4d4d7` usa `batch_alter_table`. No se ejecutaron migraciones sobre datos reales.

## Evidencia y condiciones para SaaS-02

- Copia consistente del SQLite existente, abierta como fuente `mode=ro`, e imágenes copiadas a un directorio temporal. Respaldo/restauración ejecutados exclusivamente allí: **35 imágenes vinculadas, 86 archivos; SQL completo y SHA-256 de imágenes idénticos**. Temporales eliminados; sin cambiar los originales. No demuestra seguridad bajo concurrencia ni restauración sobre un destino WAL activo.
- **36 pruebas OK**: módulos `test_agrop53_backup`, `test_agrop53_backup_integration`, `test_agrop53_backup_api`, `test_ag046_i02_security`, `test_ag046_i03_bkp05`. Ejecución con `backend/.venv`, `unittest`, directorio temporal en `AGROSCAN_DATA_DIR` y secreto JWT sintético. Tres regresiones nuevas: WAL confirmado, rollback tras fallo final y permisos revocados con JWT ya emitido. `git diff --check` OK. Build/lint frontend no aplican: sin cambios de aplicación.
- Antes de SaaS-02: autorizar alcance y definir empresa inicial para datos existentes, membresías/administrador de plataforma, unicidad de códigos/usuarios, pertenencia de dispositivos y política de respaldo global frente a respaldo por empresa.
- Criterios del siguiente incremento: migración reversible ensayada en copia con conteos/relaciones conservados; pruebas con dos empresas que nieguen cruces por ID/código, imágenes, dispositivos, revisiones y reportes; no abrir acceso multiempresa hasta cerrar riesgos críticos. PostgreSQL queda fuera de SaaS-01.
