import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator

CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,31}$")


class LotCreate(BaseModel):
    code: str
    product: Literal["mango", "tomate"]
    responsible: str = ""

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        value = value.strip()
        if not CODE_PATTERN.match(value):
            raise ValueError(
                "Usa entre 2 y 32 caracteres: letras, números, guion o guion bajo; "
                "inicia con letra o número."
            )
        return value


class LotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    product: str
    status: str
    responsible: str
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()