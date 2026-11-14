"""AG-056 I02: reviewer-only read API for unresolved cases."""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_reviewer
from ..models import User
from ..review_queue import get_review_queue

router = APIRouter(prefix='/api/reviews', tags=['AG-056 · cola de revisión'])


@router.get('/queue')
def review_queue(
    lot: str | None = Query(default=None, min_length=1, max_length=32),
    product: Literal['mango', 'tomate'] | None = None,
    priority: Literal['high', 'normal'] | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: User = Depends(require_reviewer),
):
    return get_review_queue(db, lot=lot, product=product,
                            priority=priority, limit=limit, offset=offset)
