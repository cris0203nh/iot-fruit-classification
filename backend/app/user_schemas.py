from typing import Literal

from pydantic import BaseModel, Field, field_validator


RoleName = Literal["administrador", "revisor", "operador"]


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    fullName: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=12, max_length=128)
    role: RoleName

    @field_validator("username")
    @classmethod
    def clean_username(cls, value):
        value = value.strip().lower()
        if not value:
            raise ValueError("El usuario es obligatorio.")
        return value

    @field_validator("fullName")
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("El nombre es obligatorio.")
        return value


class UserRoleUpdate(BaseModel):
    role: RoleName


class UserStatusUpdate(BaseModel):
    isActive: bool


class UserOut(BaseModel):
    id: int
    username: str
    fullName: str
    isActive: bool
    roles: list[str]
