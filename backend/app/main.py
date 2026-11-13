from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models, auto_registration_models, fruit_geometry_models, planar_calibration_models, board_calibration_models, quality_prediction_models  # noqa: F401
from .routers import auth, evaluations, images, iot, lots, users, uncertainty, review_decisions, piece_history, piece_history_report, auto_registration, fruit_geometry, planar_calibration, board_calibration, quality_prediction

app = FastAPI(title="AgroScan API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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


@app.get("/api/health")
def health():
    return {"status": "ok"}
