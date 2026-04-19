"""Do-not-call schemas."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class DNCEntryCreate(BaseModel):
    phone_number: str = Field(min_length=8, max_length=32)
    reason: str | None = None

    @field_validator("phone_number")
    @classmethod
    def normalize_phone(cls, v: str) -> str:
        return "".join(c for c in v.strip() if c.isdigit() or c == "+")


class DNCEntryResponse(BaseModel):
    id: int
    phone_number: str
    reason: str | None
    added_by_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class DNCCheckRequest(BaseModel):
    phone_number: str = Field(min_length=8, max_length=32)

    @field_validator("phone_number")
    @classmethod
    def normalize_phone(cls, v: str) -> str:
        return "".join(c for c in v.strip() if c.isdigit() or c == "+")


class DNCCheckResponse(BaseModel):
    phone_number: str
    on_dnc_list: bool
