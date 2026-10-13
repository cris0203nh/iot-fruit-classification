# AgroScan - Backend

API local (FastAPI + SQLite) de la estación AgroScan. Recibe el peso del ESP32, gestiona lotes y evaluaciones, y conserva revisiones y trazabilidad.

## Requisitos

- Python 3.11 o superior
- Git

SQLite viene incluida con Python; no se instala una base de datos aparte.

## Cómo arrancar

Desde la raíz del repositorio, en el cmd de Windows:

```
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

- API: http://127.0.0.1:8000
- Documentación para probar: http://127.0.0.1:8000/docs
- La base `backend/data/agroscan.db` se crea sola y no se sube a GitHub.

Siempre ejecuta `uvicorn` desde la carpeta `backend`.

Para que el ESP32 se conecte por Wi-Fi:

```
uvicorn app.main:app --host 0.0.0.0 --reload
```

El ESP32 envía a `http://<IP-de-la-laptop>:8000/api/iot/measurements`, en la misma red. Si Windows pide permiso en el firewall, acepta para redes privadas.

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

## Limitaciones actuales

- Sin migraciones: si cambia el modelo, borra `backend/data/agroscan.db` (solo en pruebas).
- Sin inicio de sesión: `actorId` lo envía el frontend.
- Pendientes: imágenes, adaptador de visión, estadísticas, CSV, respaldo y restauración.
- El peso enviado desde `/docs` es una simulación y no prueba la integración física.