import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import DATA_DIR, get_db
from ..evaluation_schemas import ImageOut
from ..models import Evaluation, Image

router = APIRouter(prefix="/api", tags=["imagenes"])

IMAGES_DIR = DATA_DIR / "images"
IMAGES_DIR.mkdir(exist_ok=True)

MAX_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED = {"image/jpeg": ".jpg", "image/png": ".png"}


def image_out(img: Image) -> dict:
    return {
        "id": f"I-{img.id:06d}",
        "view": img.view,
        "imageUrl": f"/api/images/I-{img.id:06d}",
    }


def parse_eval(value: str) -> int | None:
    import re
    m = re.fullmatch(r"E-(\d{1,9})", value)
    return int(m.group(1)) if m else None


@router.post("/evaluations/{evaluation_id}/images", response_model=ImageOut, status_code=201)
async def upload_image(
    evaluation_id: str,
    view: str = Form("vista-1"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    pk = parse_eval(evaluation_id)
    ev = db.get(Evaluation, pk) if pk is not None else None
    if ev is None:
        raise HTTPException(status_code=404, detail="Evaluación no encontrada.")
    if ev.status != "processing":
        raise HTTPException(status_code=409, detail="La evaluación ya no está en proceso.")
    # AGROP-26: la evidencia RGB puede asociarse a una evaluación en proceso
    # sin exigir una medición física previa. La validación de peso continúa
    # siendo responsabilidad de sus propios endpoints y del cierre del flujo.
    if file.content_type not in ALLOWED:
        raise HTTPException(status_code=422, detail="Solo se aceptan imágenes JPG o PNG.")

    view = view.strip()[:30] or "vista-1"
    content = await file.read(MAX_BYTES + 1)
    if len(content) == 0:
        raise HTTPException(status_code=422, detail="La imagen está vacía.")
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=422, detail="La imagen supera los 5 MB.")
    # No confiar exclusivamente en el Content-Type declarado por el cliente.
    is_png = content.startswith(b"\x89PNG\r\n\x1a\n") and content[-12:-8] == b"\x00\x00\x00\x00" and content[-8:-4] == b"IEND"
    is_jpeg = content.startswith(b"\xff\xd8\xff") and content.endswith(b"\xff\xd9")
    if (file.content_type == "image/png" and not is_png) or (file.content_type == "image/jpeg" and not is_jpeg):
        raise HTTPException(status_code=422, detail="El archivo no coincide con un JPG o PNG válido.")

    folder = IMAGES_DIR / f"E-{ev.id:06d}"
    folder.mkdir(exist_ok=True)
    name = f"{uuid.uuid4().hex}{ALLOWED[file.content_type]}"
    final_path = folder / name
    temp_path = folder / f"{name}.tmp"

    try:
        temp_path.write_bytes(content)
        os.replace(temp_path, final_path)  # renombrado atómico
        img = Image(
            evaluation_id=ev.id,
            view=view,
            relative_path=str(final_path.relative_to(DATA_DIR)).replace("\\", "/"),
            content_type=file.content_type,
            size_bytes=len(content),
        )
        db.add(img)
        ev.image_count = (ev.image_count or 0) + 1
        db.commit()
        db.refresh(img)
    except Exception:
        db.rollback()
        for p in (temp_path, final_path):
            if p.exists():
                p.unlink()
        raise HTTPException(status_code=500, detail="No se pudo guardar la imagen.")

    return image_out(img)


@router.get("/images/{image_id}")
def get_image(image_id: str, db: Session = Depends(get_db)):
    import re
    m = re.fullmatch(r"I-(\d{1,9})", image_id)
    img = db.get(Image, int(m.group(1))) if m else None
    if img is None:
        raise HTTPException(status_code=404, detail="Imagen no encontrada.")
    path = DATA_DIR / img.relative_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Evidencia no disponible: el archivo falta.")
    return FileResponse(path, media_type=img.content_type)