from typing import Literal

from pydantic import BaseModel, field_validator

from .evaluation_schemas import EvaluationDetailOut


def _clean(value: str, max_len: int, label: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{label} es obligatorio.")
    if len(value) > max_len:
        raise ValueError(f"{label} admite hasta {max_len} caracteres.")
    return value


class ReviewCreate(BaseModel):
    actorId: str
    reason: str
    newValue: str

    @field_validator("actorId")
    @classmethod
    def v_actor(cls, v: str) -> str:
        return _clean(v, 64, "El responsable")

    @field_validator("reason")
    @classmethod
    def v_reason(cls, v: str) -> str:
        return _clean(v, 500, "El motivo")

    @field_validator("newValue")
    @classmethod
    def v_value(cls, v: str) -> str:
        return _clean(v, 50, "El nuevo valor")


class CancelCreate(BaseModel):
    actorId: str
    reason: str

    @field_validator("actorId")
    @classmethod
    def v_actor(cls, v: str) -> str:
        return _clean(v, 64, "El responsable")

    @field_validator("reason")
    @classmethod
    def v_reason(cls, v: str) -> str:
        return _clean(v, 500, "El motivo")


class ReviewEventOut(BaseModel):
    id: str
    performedAt: str
    actorId: str
    type: Literal["review", "cancellation"]
    reason: str
    previousValue: str | None
    updatedValue: str | None


class TraceabilityOut(BaseModel):
    evaluation: EvaluationDetailOut
    calibrationReference: str | None
    modelVersion: str | None
    rulesVersion: str | None
    reviews: list[ReviewEventOut]