# AgroScan - Backend

API local (FastAPI + SQLite) de la estación AgroScan. Recibe el peso del ESP32, gestiona lotes y evaluaciones, y conserva revisiones y trazabilidad.

## Requisitos

- Python 3.11 o superior
- Git

SQLite viene incluida con Python; no se instala una base de datos aparte.

## Cómo arrancar

Desde la raíz del repositorio, con PowerShell (entorno local):

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Configurar AGROSCAN_JWT_SECRET mediante backend/.env local o variable de entorno.
# Debe ser secreto, único y tener al menos 32 caracteres; nunca publicarlo.
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- API local: http://127.0.0.1:8000
- Documentación interactiva: http://127.0.0.1:8000/docs
- Persistencia: `backend/data/agroscan.db`, que **no** debe subirse a Git ni borrarse para resolver errores.

**Inicialización y migraciones:** el proyecto ya contiene Alembic. Para una instalación nueva, revisar el historial y ejecutar desde `backend`:

```powershell
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Antes de migrar una base existente, realizar y verificar un respaldo, comprobar el estado de las migraciones y revisar cambios de esquema. **No borrar** `backend/data/agroscan.db` ni reemplazarla con una base de pruebas. El arranque normal de Uvicorn no sustituye las migraciones ni el aprovisionamiento de usuarios.

**Red y puente IoT:** el firmware versionado usa USB/serie y un puente HTTP (véase `firmware/tools` y la guía en `docs/AGROP-21-AGROP-23-pesaje.md`); no asumir conectividad Wi-Fi directa. `POST /api/iot/measurements` aún admite solicitudes sin credencial de dispositivo (AG-046 SEC-11). Por ello, usar `127.0.0.1` y un puente local de confianza; no publicar la API en `0.0.0.0`, LAN pública, túneles o Internet sin implementar y probar autenticación/aislamiento de red. CORS no sustituye autenticación.

Para la demo, la rama Vercel admite orígenes HTTPS exactos mediante `AGROSCAN_DEMO_ORIGINS`; esta configuración controla navegadores, no evita solicitudes HTTP directas.

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | /api/health | Estado del backend |
| GET | /api/lots | Listar lotes |
| POST | /api/lots | Crear lote |
| GET | /api/lots/{id} | Consultar lote |
| GET | /api/evaluations | Historial (filtros lot, product, status) |
| POST | /api/evaluations | Crear evaluación |
| GET | /api/evaluations/{id} | Detalle |
| GET | /api/evaluations/{id}/traceability | Trazabilidad |
| POST | /api/evaluations/{id}/reviews | Registrar revisión |
| POST | /api/evaluations/{id}/cancel | Anular |
| POST | /api/evaluations/{id}/weight/pre | Peso inicial |
| POST | /api/evaluations/{id}/weight/post | Peso de confirmación |
| POST | /api/iot/measurements | Recibir peso del ESP32 |
| GET | /api/iot/status | Estado del sensor |

Detalle de solicitudes y respuestas: `docs/api-contract.md`.

## Autenticación, roles y respaldo

- `POST /api/auth/login`: acceso con usuario y contraseña; JWT HS256. Configurar `AGROSCAN_JWT_SECRET` y respetar los roles `administrador`, `operador` y `revisor`. El frontend mantiene el token en memoria, no en almacenamiento persistente.
- Los endpoints de captura requieren operador/administrador; las decisiones formales de revisión requieren revisor/administrador; las operaciones de usuario y respaldo se reservan al administrador.
- `POST /api/admin/backups`: crear un ZIP verificado con SQLite e imágenes; `POST /api/admin/backups/restore`: restaurar con comprobaciones de hash, rutas y rollback. La restauración es destructiva: validar primero en una copia aislada y conservar un respaldo previo.
- El guard de escrituras AG-046 BKP-05 limita operaciones concurrentes en **un proceso FastAPI**. No es una exclusión compartida entre workers ni protege procesos que escriban SQLite fuera de la API.

## Limitaciones comprobadas y pendientes

- **SEC-11:** falta autenticar o aislar formalmente la ingesta IoT para despliegues accesibles desde otras redes. No exponer esa ruta en Internet.
- **SEC-12:** pendiente aprobar la política para anotaciones experimentales hechas por operadores frente a decisiones humanas formales de revisores.
- La integridad SHA-256 se verifica donde existen snapshots de procedencia; no todas las fotografías históricas tienen un hash de captura universal.
- Las pruebas AG-046 I02–I04 usan usuarios, datos SQLite y fotografías sintéticos. No acreditan el hardware, los modelos, Render, Vercel, múltiples workers, navegadores reales ni el corte de energía a mitad de una transacción.
- El peso enviado manualmente desde `/docs` no demuestra la integración física del dispositivo.

Revisar `docs/ag046/AG046_I05_CIERRE_EVIDENCIADO.md` y su matriz de pendientes antes de declarar completada una instalación.
