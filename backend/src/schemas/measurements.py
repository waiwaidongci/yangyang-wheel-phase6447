from pydantic import BaseModel, ConfigDict, Field, FiniteFloat


class MeasurementCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    scan_id: str = Field(min_length=1, max_length=64)
    angle_deg: FiniteFloat = Field(ge=0, le=360)
    measured_mm: FiniteFloat = Field(ge=-20, le=20)
