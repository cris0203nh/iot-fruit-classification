from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401
from .routers import auth, evaluations, images, iot, lots, users, uncertainty, review_decisions, piece_history

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


@app.get("/api/health")
def health():
    return {"status": "ok"}
