from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_authenticated, require_operator
from ..models import Lot, User
from ..schemas import LotCreate, LotOut

router = APIRouter(prefix="/api/lots", tags=["lotes"])


@router.get("", response_model=list[LotOut])
def list_lots(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_authenticated),
):
    return db.scalars(select(Lot).order_by(Lot.id.desc())).all()


@router.post("", response_model=LotOut, status_code=201)
def create_lot(
    payload: LotCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_operator),
):
    exists = db.scalar(
        select(Lot).where(func.lower(Lot.code) == payload.code.lower())
    )

    if exists:
        raise HTTPException(
            status_code=409,
            detail="Ya existe un lote con esa referencia.",
        )

    lot = Lot(
        code=payload.code,
        product=payload.product,
        responsible=payload.responsible.strip(),
    )

    db.add(lot)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Ya existe un lote con esa referencia.",
        )

    db.refresh(lot)
    return lot


@router.get("/{lot_id}", response_model=LotOut)
def get_lot(
    lot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_authenticated),
):
    lot = db.get(Lot, lot_id)

    if lot is None:
        raise HTTPException(
            status_code=404,
            detail="Lote no encontrado.",
        )

    return lot