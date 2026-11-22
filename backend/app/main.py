import os
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from .dependencies import require_operational_context, block_global_operations
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler

from .services.capture_control import capture_operation
from fastapi.middleware.cors import CORSMiddleware

from . import models, auto_registration_models, fruit_geometry_models, planar_calibration_models, board_calibration_models, quality_prediction_models  # noqa: F401
from .routers import auth, evaluations, images, iot, lots, users, uncertainty, review_decisions, piece_history, piece_history_report, auto_registration, fruit_geometry, planar_calibration, board_calibration, quality_prediction, review_queue, backup
from .routers import platform
from .routers import auth_identity, invitations
from .routers import iot_admin, organization_export
from .routers import commercial
from .routers import applications
from .services.browser_sessions import COOKIE as SESSION_COOKIE, protect_browser_request

app = FastAPI(title="AgroScan API", dependencies=[Depends(protect_browser_request)])
app.add_middleware(applications.ApplicationBodyLimit)


@app.middleware('http')
async def prevent_private_session_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith('/api/auth/') or SESSION_COOKIE in request.cookies:
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.exception_handler(RequestValidationError)
async def protect_platform_validation_inputs(request: Request, exc: RequestValidationError):
    if request.url.path.startswith(('/api/platform/', '/api/auth/google', '/api/auth/invitations', '/api/invitations', '/api/iot/')):
        # No devolver contraseñas ni cuerpos completos en errores del alta privada.
        errors = [{key: error[key] for key in ('loc', 'msg', 'type')} for error in exc.errors()]
        return JSONResponse(status_code=422, content={'detail': errors})
    return await request_validation_exception_handler(request, exc)

# AG-046 BKP-05: proteger escrituras durante respaldo/restauración.
# El estado está en memoria y protege SOLO un proceso FastAPI.
_MUTATING_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})
_BACKUP_OPERATIONS = frozenset({
    '/api/admin/backups',
    '/api/admin/backups/restore',
})


@app.middleware('http')
async def protect_writes_during_backup(request: Request, call_next):
    path = request.url.path
    if (request.method not in _MUTATING_METHODS
            or not path.startswith('/api/')
            or path in _BACKUP_OPERATIONS):
        return await call_next(request)

    # Mantener el guard hasta completar la solicitud, no solo al inicio.
    try:
        with capture_operation():
            return await call_next(request)
    except HTTPException as exc:
        # Las excepciones lanzadas desde middleware se responden aquí.
        return JSONResponse(
            status_code=exc.status_code,
            content={'detail': exc.detail},
            headers=exc.headers,
        )


def _demo_cors_origins() -> list[str]:
    # Solo origenes HTTPS exactos; nunca usar * en una API expuesta por tunel.
    origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
    for raw in os.environ.get("AGROSCAN_DEMO_ORIGINS", "").split(","):
        value = raw.strip().rstrip("/")
        if not value:
            continue
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.path or parsed.query or parsed.fragment):
            raise RuntimeError("AGROSCAN_DEMO_ORIGINS: se exige origen HTTPS exacto")
        if value not in origins:
            origins.append(value)
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_demo_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
    expose_headers=['X-AgroScan-Session-Invalid'],
)

app.include_router(auth.router)
app.include_router(auth_identity.router)
app.include_router(platform.router)
app.include_router(commercial.router)
app.include_router(commercial.owner)
app.include_router(applications.public)
app.include_router(applications.owner)
operational = APIRouter(dependencies=[Depends(require_operational_context)])
for router in (users.router, lots.router, evaluations.router, images.router,
               uncertainty.router, review_decisions.router, piece_history.router,
               piece_history_report.router, auto_registration.router, fruit_geometry.router,
               planar_calibration.router, board_calibration.router, quality_prediction.router,
               review_queue.router, invitations.router, iot_admin.router, organization_export.router):
    operational.include_router(router)
app.include_router(operational)
app.include_router(iot.router)
app.include_router(backup.router, dependencies=[Depends(block_global_operations)])


@app.get("/api/health")
def health():
    return {"status": "ok"}
