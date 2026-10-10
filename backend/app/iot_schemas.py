from pydantic import BaseModel, Field


class MeasurementCreate(BaseModel):
    schema_version: int = 1
    device_id: str = Field(min_length=1, max_length=64)
    boot_id: str = Field(min_length=1, max_length=64)
    seq: int = Field(ge=0)
    weight_g: float = Field(ge=0, le=5000)
    stable: bool
    calibration_version: str = Field(min_length=1, max_length=64)


class MeasurementOut(BaseModel):
    received: bool
    duplicate: bool
    receivedAt: str


class IotStatusOut(BaseModel):
    online: bool
    deviceId: str | None
    weightG: float | None
    stable: bool | None
    receivedAt: str | None
    ageSeconds: float | None