from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401
from .http_security import HttpSecurityHeadersMiddleware
from .routers import auth, evaluations, images, iot, lots, users

app = FastAPI(title="AgroScan API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Último middleware registrado = primero en el trayecto de respuesta.
# También cubre respuestas de preflight generadas por CORSMiddleware.
app.add_middleware(HttpSecurityHeadersMiddleware)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(lots.router)
app.include_router(evaluations.router)
app.include_router(iot.router)
app.include_router(images.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
