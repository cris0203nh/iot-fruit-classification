import os
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models, auto_registration_models, fruit_geometry_models, planar_calibration_models, board_calibration_models, quality_prediction_models  # noqa: F401
from .routers import auth, evaluations, images, iot, lots, users, uncertainty, review_decisions, piece_history, piece_history_report, auto_registration, fruit_geometry, planar_calibration, board_calibration, quality_prediction, review_queue, backup

app = FastAPI(title="AgroScan API")

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
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(lots.router)
app.include_router(evaluations.router)
app.include_router(iot.router)
app.include_router(images.router)
app.include_router(uncertainty.router)
app.include_router(review_decisions.router)
app.include_router(piece_history.router)
app.include_router(piece_history_report.router)
app.include_router(auto_registration.router)
app.include_router(fruit_geometry.router)
app.include_router(planar_calibration.router)
app.include_router(board_calibration.router)
app.include_router(quality_prediction.router)
app.include_router(review_queue.router)
app.include_router(backup.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
