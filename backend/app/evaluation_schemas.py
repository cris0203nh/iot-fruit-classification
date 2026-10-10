import re
from typing import Literal

from pydantic import BaseModel, field_validator

PIECE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class EvaluationCreate(BaseModel):
    lotId: str  # referencia del lote, ej. LOTE-001
    pieceId: str

    @field_validator("pieceId")
    @classmethod
    def validate_piece(cls, value: str) -> str:
        value = value.strip()
        if not PIECE_PATTERN.match(value):
            raise ValueError(
                "La pieza debe tener hasta 64 caracteres: letras, números, "
                "punto, guion o guion bajo; inicia con letra o número."
            )
        return value

    @field_validator("lotId")
    @classmethod
    def clean_lot(cls, value: str) -> str:
        return value.strip()


class EvidenceOut(BaseModel):
    id: str
    view: str
    imageUrl: str


class EvaluationSummaryOut(BaseModel):
    id: str
    lotId: str
    pieceId: str
    product: Literal["mango", "tomate"]
    registeredAt: str
    status: Literal["processing", "completed", "pending_review", "error", "cancelled"]
    weightGrams: float | None
    imageCount: int


class EvaluationDetailOut(EvaluationSummaryOut):
    evidence: list[EvidenceOut]
    visualCategory: str | None
    reviewNote: str | None