
import os
import re
import uuid
import threading
from pathlib import Path

import cv2
import numpy as np

from fastapi import (
    APIRouter, Depends, File, Form, Header,
    HTTPException, UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import DATA_DIR, get_db
from ..dependencies import require_authenticated, require_operator
from ..evaluation_schemas import ImageOut
from ..models import User, Evaluation, Image

router = APIRouter(prefix="/api", tags=["imagenes"])

IMAGES_DIR = DATA_DIR / "images"

MAX_BYTES = 5 * 1024 * 1024
ALLOWED = {"image/jpeg": ".jpg", "image/png": ".png"}


def image_out(img: Image) -> dict:
    return {
        "id": f"I-{img.id:06d}",
        "view": img.view,
        "imageUrl": f"/api/images/I-{img.id:06d}",
    }


def parse_eval(value: str) -> int | None:
    match = re.fullmatch(r"E-(\d{1,9})", value)
    return int(match.group(1)) if match else None


@router.post(
    "/evaluations/{evaluation_id}/images",
    response_model=ImageOut,
    status_code=201,
)
async def upload_image(
    evaluation_id: str,
    view: str = Form("vista-1"),
    file: UploadFile = File(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    if not re.fullmatch(r"[a-f0-9]{64}", idempotency_key):
        raise HTTPException(
            status_code=422,
            detail="La clave de idempotencia debe tener 64 caracteres hexadecimales.",
        )

    pk = parse_eval(evaluation_id)
    ev = db.get(Evaluation, pk) if pk is not None else None

    if ev is None:
        raise HTTPException(status_code=404, detail="Evaluación no encontrada.")

    # Reintento: devolver la evidencia original sin crear otra.
    existing = db.scalar(
        select(Image).where(
            Image.evaluation_id == ev.id,
            Image.idempotency_key == idempotency_key,
        )
    )

    if existing is not None:
        return image_out(existing)

    if ev.status != "processing":
        raise HTTPException(
            status_code=409,
            detail="La evaluación ya no está en proceso.",
        )

    if file.content_type not in ALLOWED:
        raise HTTPException(
            status_code=422,
            detail="Solo se aceptan imágenes JPG o PNG.",
        )

    view = view.strip()[:30] or "vista-1"

    content = await file.read(MAX_BYTES + 1)

    if not content:
        raise HTTPException(status_code=422, detail="La imagen está vacía.")

    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=422, detail="La imagen supera los 5 MB.")

    is_png = (
        content.startswith(b"\x89PNG\r\n\x1a\n")
        and content[-12:-8] == b"\x00\x00\x00\x00"
        and content[-8:-4] == b"IEND"
    )

    is_jpeg = content.startswith(b"\xff\xd8\xff") and content.endswith(b"\xff\xd9")

    if (
        file.content_type == "image/png" and not is_png
    ) or (
        file.content_type == "image/jpeg" and not is_jpeg
    ):
        raise HTTPException(
            status_code=422,
            detail="El archivo no coincide con un JPG o PNG válido.",
        )

    folder = IMAGES_DIR / f"E-{ev.id:06d}"
    name = f"{uuid.uuid4().hex}{ALLOWED[file.content_type]}"

    final_path = folder / name
    temp_path = folder / f"{name}.tmp"

    try:
        folder.mkdir(parents=True, exist_ok=True)

        # Primero guardar temporalmente.
        temp_path.write_bytes(content)

        # Publicar el archivo mediante renombrado atómico.
        os.replace(temp_path, final_path)

        img = Image(
            evaluation_id=ev.id,
            view=view,
            relative_path=str(
                final_path.relative_to(DATA_DIR)
            ).replace("\\", "/"),
            content_type=file.content_type,
            size_bytes=len(content),
            idempotency_key=idempotency_key,
        )

        db.add(img)
        ev.image_count = (ev.image_count or 0) + 1

        # Obtener el ID antes de confirmar la transacción.
        db.flush()
        db.commit()

    except IntegrityError:
        db.rollback()

        for path in (temp_path, final_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

        # Otra solicitud pudo registrar la misma clave simultáneamente.
        existing = db.scalar(
            select(Image).where(
                Image.evaluation_id == ev.id,
                Image.idempotency_key == idempotency_key,
            )
        )

        if existing is not None:
            return image_out(existing)

        raise HTTPException(
            status_code=500,
            detail="No se pudo confirmar el registro de la imagen.",
        )

    except Exception:
        db.rollback()

        for path in (temp_path, final_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

        raise HTTPException(
            status_code=500,
            detail="No se pudo guardar la imagen.",
        )

    return image_out(img)




# =====================================================
# AGROSCAN: DETECCI?N Y SEGMENTACI?N YOLOE EN VIVO
# =====================================================

from app.services.live_frame_pipeline import evaluate_live_frame


VISION_ROOT = Path(__file__).resolve().parents[3]
VISION_WEIGHTS = VISION_ROOT / "vision" / "models" / "yoloe-26n-seg.pt"
VISION_PROMPTS = VISION_ROOT / "vision" / "models" / "agroscan_mango_tomato_prompts.npz"

VISION_CLASSES = ["mango fruit", "tomato fruit"]

_VISION_MODEL = None
_VISION_INIT_LOCK = threading.Lock()
_VISION_INFERENCE_LOCK = threading.Lock()


def get_vision_model():
    global _VISION_MODEL

    if _VISION_MODEL is None:
        with _VISION_INIT_LOCK:
            if _VISION_MODEL is None:
                from ultralytics import YOLOE

                if not VISION_WEIGHTS.is_file():
                    raise RuntimeError("Faltan los pesos YOLOE.")

                model = YOLOE(str(VISION_WEIGHTS))

                if VISION_PROMPTS.is_file():
                    model.load_prompt_embeddings(str(VISION_PROMPTS))
                else:
                    model.set_classes(VISION_CLASSES)

                _VISION_MODEL = model

    return _VISION_MODEL


@router.post("/evaluations/{evaluation_id}/vision/detect")
def detect_evaluation_frame(
    evaluation_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    pk = parse_eval(evaluation_id)
    ev = db.get(Evaluation, pk) if pk is not None else None

    if ev is None:
        raise HTTPException(404, "Evaluaci?n no encontrada.")

    if ev.status != "processing":
        raise HTTPException(409, "La evaluaci?n ya no est? en proceso.")

    if ev.product not in ("mango", "tomate"):
        raise HTTPException(422, "Producto no compatible.")

    if file.content_type != "image/jpeg":
        raise HTTPException(422, "La c?mara debe enviar JPEG.")

    content = file.file.read(2 * 1024 * 1024 + 1)

    if not content or len(content) > 2 * 1024 * 1024:
        raise HTTPException(422, "Fotograma vac?o o demasiado grande.")

    frame = cv2.imdecode(
        np.frombuffer(content, dtype=np.uint8),
        cv2.IMREAD_COLOR
    )

    if frame is None:
        raise HTTPException(422, "No se pudo decodificar el fotograma.")

    try:
        model = get_vision_model()

        with _VISION_INFERENCE_LOCK:
            result = model.predict(
                source=frame,
                imgsz=512,
                conf=0.25,
                iou=0.50,
                max_det=10,
                device="cpu",
                verbose=False
            )[0]

        candidates = []
        names = result.names

        if result.boxes is not None:
            for index, box in enumerate(result.boxes):
                class_id = int(box.cls[0].item())

                label = (
                    names.get(class_id, "")
                    if isinstance(names, dict)
                    else names[class_id]
                )

                label = str(label).lower()

                if ev.product == "mango" and "mango" not in label:
                    continue

                if ev.product == "tomate" and not any(
                    word in label for word in ("tomato", "tomate")
                ):
                    continue

                confidence = float(box.conf[0].item())

                coordinates = [
                    float(value)
                    for value in box.xyxy[0].tolist()
                ]

                polygon = []

                if result.masks is not None:
                    polygons = result.masks.xy

                    if index < len(polygons):
                        points = polygons[index]

                        stride = max(1, len(points) // 120)

                        polygon = [
                            [
                                round(float(point[0]), 1),
                                round(float(point[1]), 1)
                            ]
                            for point in points[::stride]
                        ]

                candidates.append({
                    "box": coordinates,
                    "confidence": confidence,
                    "polygon": polygon
                })

        candidates.sort(
            key=lambda item: item["confidence"],
            reverse=True
        )

        selected = candidates[0] if candidates else None

        ready = (
            len(candidates) == 1
            and selected is not None
            and selected["confidence"] >= 0.40
            and len(selected["polygon"]) >= 3
        )

        visual_analysis = None

        if ready and selected is not None:
            try:
                visual_analysis = evaluate_live_frame(
                    product=ev.product,
                    frame_bgr=frame,
                    polygon=selected["polygon"],
                )
            except (ValueError, TypeError) as exc:
                visual_analysis = {
                    "analysis_status": "pendiente_revision",
                    "reason": str(exc),
                    "human_review_required": True,
                }
            except Exception as exc:
                visual_analysis = {
                    "analysis_status": "error",
                    "reason": type(exc).__name__,
                    "human_review_required": True,
                }

        return {
            "detected": selected is not None,
            "readyToCapture": ready,
            "product": ev.product,
            "confidence": selected["confidence"] if selected else None,
            "box": selected["box"] if selected else None,
            "polygon": selected["polygon"] if selected else [],
            "candidateCount": len(candidates),
            "frameWidth": int(frame.shape[1]),
            "frameHeight": int(frame.shape[0]),
            "visualAnalysis": visual_analysis,
            "reason": (
                "deteccion_unica"
                if ready
                else "varias_frutas"
                if len(candidates) > 1
                else "deteccion_no_confirmada"
            )
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Detector YOLOE no disponible: {type(exc).__name__}"
        ) from exc


@router.get("/images/{image_id}")
def get_image(
    image_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_authenticated),
):
    match = re.fullmatch(r"I-(\d{1,9})", image_id)
    img = db.get(Image, int(match.group(1))) if match else None

    if img is None:
        raise HTTPException(status_code=404, detail="Imagen no encontrada.")

    path = DATA_DIR / img.relative_path

    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Evidencia no disponible: el archivo falta.",
        )

    return FileResponse(path, media_type=img.content_type)
