# AG-046 / AGROP-54 — Incremento 01: auditoría inicial

**Corte:** 2026-11-16 (America/Lima)
**Repositorio:** [https://github.com/cris0203nh/iot-fruit-classification](https://github.com/cris0203nh/iot-fruit-classification)
**Rama/commit auditado:** `main` / [`1d3b66b7017f`](https://github.com/cris0203nh/iot-fruit-classification/commit/1d3b66b7017f7f9139a5a35521f458bf100f6a66)
**Método:** lectura del código versionado y revisión de pruebas existentes mediante GitHub; **no se ejecutó la aplicación, las pruebas, ni se inspeccionó la base SQLite local**.
**Estado I01:** documentación de auditoría estática completada; todas las verificaciones dinámicas quedan pendientes. **AG-046 no se declara aceptada ni cerrada.**

## 1. Objetivo y límites

Objetivo: disponer de un inventario reproducible de controles de autenticación/autorización, integridad de relaciones y archivos, respaldo/restauración y persistencia después de reiniciar. La evidencia exigida por Jira consiste en **checklist técnico y registro de bugs**. Dependencias declaradas por el ticket: AG-039 (seguridad) y AG-045 (respaldo y restauración).

No incluye nuevos permisos, correcciones de defectos, ejecución destructiva, cambios a datos reales, pruebas de hardware ni validación experimental del clasificador E0/E1/E2. Un control identificado en código **no equivale a un control aprobado en ejecución**.

## 2. Dependencias e historia reutilizable

- **AG-039:** autenticación JWT, Argon2, roles en `security.py`, `dependencies.py`, rutas y tests de permisos; [PR #31](https://github.com/cris0203nh/iot-fruit-classification/pull/31) fusionado.
- **AG-045:** respaldos ZIP con SQLite e imágenes, manifiesto SHA-256, validación previa y rollback; [PR #79](https://github.com/cris0203nh/iot-fruit-classification/pull/79) fusionado.
- **Regresión complementaria:** recuperación de sensor, imágenes y disco, [PR #78](https://github.com/cris0203nh/iot-fruit-classification/pull/78) fusionado; cola de revisión [PR #77](https://github.com/cris0203nh/iot-fruit-classification/pull/77) y entrega I01-I05 [PR #80](https://github.com/cris0203nh/iot-fruit-classification/pull/80), fusionados.
- Las evidencias previas corresponden a otros cortes de código: requieren reejecución selectiva cuando se ejecuten I02-I04; no se trasladan recuentos como resultados de AG-046.

## 3. Inventario de superficies API

El inventario estático encuentra **17 routers, 57 operaciones declaradas y 1 ruta `health`**, para **58 endpoints declarados** en los archivos importados por `backend/app/main.py`. No se ha obtenido `/openapi.json` en un servidor en marcha, por lo que la cantidad debe cotejarse dinámicamente en I02.

| Archivo (routers/) | Rutas | Regla visible en código |
|---|---:|---|
| `auth.py` | 2 | Login: público; /me: autenticado |
| `users.py` | 4 | Administrador |
| `lots.py` | 3 | GET: autenticado; POST: operador/administrador |
| `evaluations.py` | 9 | Lectura: autenticado; crear/pesar/confirmar: operador; revisar: revisor; anular: administrador |
| `images.py` | 3 | Subir/detectar: operador; consultar: autenticado |
| `iot.py` | 2 | Recepción y estado: sin autenticación de usuario en código |
| `uncertainty.py` | 3 | Gate: autenticado (forceReview restringe revisor); consultar: autenticado; resolver: revisor |
| `review_decisions.py` | 2 | Consultar: autenticado; registrar: revisor |
| `piece_history.py` | 2 | Autenticado |
| `piece_history_report.py` | 1 | Autenticado |
| `auto_registration.py` | 2 | Operador y guardia de captura |
| `fruit_geometry.py` | 2 | Leer: autenticado; analizar: operador |
| `planar_calibration.py` | 2 | Leer: autenticado; medir: operador |
| `board_calibration.py` | 6 | Leer: autenticado; escribir: operador; reporte: revisor |
| `quality_prediction.py` | 11 | Leer: autenticado; analizar: operador; anotación experimental: operador (revisar requisito) |
| `review_queue.py` | 1 | Revisor |
| `backup.py` | 2 | Administrador |
| `main.py` | 1 | `GET /api/health`, pública |

**Convención de roles en código:** `require_admin`=administrador; `require_reviewer`=administrador/revisor; `require_operator`=administrador/operador; `require_authenticated`=administrador/revisor/operador. Las rutas con dependencias a nivel de router (por ejemplo respaldos) también están protegidas, aunque su función no repita `Depends`.

## 4. Controles observados en el código

### 4.1. Identidad y sesiones

- `backend/app/security.py`: secreto JWT obligatorio con longitud mínima de 32 caracteres, algoritmo HS256, `sub`/`iat`/`exp`, caducidad por defecto de 30 minutos, hash/validación de contraseñas con Argon2 mediante `pwdlib`.
- `backend/app/dependencies.py`: rechaza usuarios inexistentes/inactivos, define autorización por roles y diferencia HTTP 401/403.
- `frontend/src/services/agroscanApi.ts`: token de sesión en memoria, enviado mediante cabecera `Authorization: Bearer`. No se guarda en `localStorage` según el código leído.
- Existen pruebas de rutas de revisión/anulación con diferentes roles y de administración de respaldos. **No se acreditan aquí los resultados de su ejecución sobre el HEAD actual.**

### 4.2. SQLite, archivos y trazabilidad

- `backend/app/database.py`: SQLite persistente en `backend/data/agroscan.db` y activación de `PRAGMA foreign_keys=ON` en las conexiones.
- `backend/app/services/backup_service.py`: `PRAGMA integrity_check`, `PRAGMA foreign_key_check`, cotejo de relaciones `images.relative_path`, copia consistente de SQLite y manifiesto SHA-256 de base e imágenes.
- `backend/app/routers/images.py`: validación declarada de tipo/tamaño, escritura temporal seguida de `os.replace`, idempotencia y limpieza ante excepciones; publicación de imágenes mediante endpoint autenticado.
- `backend/app/routers/review_decisions.py`: verifica origen y SHA-256 antes de registrar decisiones auditables.
- `backend/app/routers/piece_history_report.py`: hash SHA-256 del CSV de reporte, no necesariamente hash físico de todos los archivos originales.
- `backend/alembic/versions/` contiene migraciones; la documentación inicial de `backend/README.md` no refleja ese estado.

### 4.3. Respaldos y reinicio

- `backend/app/routers/backup.py`: creación y restauración reservadas al administrador; suspensión de captura, ZIP cargado temporalmente y límite de carga de 2 GB.
- `backend/app/services/backup_service.py`: límite de entradas y tamaño descomprimido, rechazo de rutas inseguras, verificación de manifiesto, restauración escalonada y rollback ante errores.
- `backend/app/services/capture_control.py`: exclusión intra-proceso para operaciones protegidas por `capture_guard`; **no implica por sí sola exclusión de todas las escrituras de todos los endpoints**.
- La base está en disco, pero **se necesita prueba de parada/reinicio real y comparación antes/después** de lotes, evaluaciones, imágenes y revisiones.

## 5. Hallazgos y decisiones abiertas

| ID | Hallazgo respaldado por código | Naturaleza | Prioridad de examen | Próximo paso |
|---|---|---|---|---|
| AG046-H01 | `POST /api/iot/measurements` y `GET /api/iot/status` no emplean autenticación en el código de sus rutas | Superficie abierta; riesgo condicionado a exposición de red | Alta si se despliega públicamente | Definir frontera LAN/Internet y probar acceso; diseñar autenticación de dispositivo si aplica |
| AG046-H02 | `suspend_capture()` solo coordina operaciones que se registran; varias escrituras de evaluaciones/revisiones/IoT no muestran `capture_guard` | Riesgo de concurrencia durante restauración, **no reproducido** | Alta | Prueba de escrituras durante restauración en entorno aislado |
| AG046-H03 | El POST de anotación E0/E1/E2 en `quality_prediction.py` exige `require_operator`, mientras decisiones humanas de `review_decisions.py` exigen `require_reviewer` | Diferencia de roles entre flujos; intención funcional por confirmar | Media | Validar matriz de autorización esperada; no igualar ambos flujos sin decidir requisitos |
| AG046-H04 | `backend/README.md` declara que no hay login/migraciones/respaldo aunque el código los implementa | Defecto documental confirmado por comparación con código | Baja | Corregir documentación en I05 |
| AG046-H05 | Las pruebas existentes cubren fallos y restauración, pero no hay prueba acreditada de reinicio completo del proceso con comparación de todas las entidades | Brecha de evidencia; no se afirma ausencia absoluta de prueba fuera del repo | Media | Ejecutar prueba de reinicio con comprobantes en I04 |
| AG046-H06 | La consulta de imagen verifica existencia del archivo, mientras la verificación SHA de originales aparece en flujos concretos | Cobertura de integridad por endpoint pendiente de determinar | Media | Definir política de hashes, probar archivo alterado e imagen ausente |

**Clasificación:** H01-H03/H06 son candidatos para evaluación y posible registro de bugs tras reproducir y acordar el comportamiento esperado. H04 es defecto de documentación observable. H05 es brecha de evidencia. Ninguno se declara corregido.

## 6. Condiciones de ejecución posterior

1. Trabajar en rama `feature/AGROP-54-auditoria-inicial-checklist` u otra rama específica; no publicar directamente en `main`.
2. Antes de pruebas destructivas de I03/I04, crear un entorno aislado con SQLite, imágenes y un conjunto de datos sintéticos identificables como prueba. No borrar ni sobreescribir `backend/data/agroscan.db` del usuario.
3. Registrar por control: versión/commit, fecha, comando, salida completa, código HTTP, capturas (si aplica), resultado esperado/obtenido y responsable.
4. Guardar evidencias de ejecución en directorio excluido de Git si contienen JWT, credenciales, fotos no autorizadas o datos personales. Solo subir resúmenes depurados y sin secretos.
5. Antes de cerrar AG-046, ejecutar las pruebas de regresión pertinentes y resolver o aceptar formalmente los defectos de severidad alta/crítica.

## 7. Salida de I01 y traspaso

**Entregados en este incremento:** este informe de auditoría estática, `AG046_I01_CHECKLIST.md`, `AG046_I01_MATRIZ_CONTROLES.csv`, `AG046_I01_REGISTRO_HALLAZGOS.md`, `AG046_I01_REGISTRO_BUGS.csv` y protocolo de evidencias.
**Pendiente para I02:** ejecutar controles de identidad y permisos en un entorno real de pruebas; el resultado aún debe consignarse en el checklist, no presumirse aprobado por existir tests anteriores.
**Pendiente para I03/I04:** pruebas de consistencia, recuperación, concurrencia y reinicio.
**Pendiente para I05:** arreglos confirmados, revisión de regresiones, actualización de README, evidencias y cierre Jira.
