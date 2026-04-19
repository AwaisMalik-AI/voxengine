"""Campaign and recipient schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.voice import CampaignStatus, RecipientStatus


class CampaignRecipientCreate(BaseModel):
    phone_number: str = Field(min_length=8, max_length=32)
    name: str | None = Field(default=None, max_length=256)
    variables: dict[str, Any] | None = None

    @field_validator("phone_number")
    @classmethod
    def normalize_phone(cls, v: str) -> str:
        return "".join(c for c in v.strip() if c.isdigit() or c == "+")


class CampaignRecipientBulk(BaseModel):
    recipients: list[CampaignRecipientCreate] = Field(min_length=1, max_length=10_000)


class CampaignRecipientResponse(BaseModel):
    id: int
    campaign_id: int
    phone_number: str
    name: str | None
    variables: dict[str, Any] | None
    status: RecipientStatus
    call_duration_seconds: float | None
    error_message: str | None
    attempted_at: datetime | None
    twilio_call_sid: str | None

    model_config = {"from_attributes": True}


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    description: str | None = None
    voice_profile_id: int
    message_template: str = Field(
        min_length=1,
        max_length=20_000,
        description="Template with {{name}}, {{phone_number}}, and custom {{variable}} placeholders",
    )
    webhook_url: str | None = Field(default=None, max_length=1024)
    scheduled_at: datetime | None = None
    recipients: list[CampaignRecipientCreate] | None = Field(
        default=None,
        description="Optional initial recipient list (same as bulk add)",
    )


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=256)
    description: str | None = None
    voice_profile_id: int | None = None
    message_template: str | None = Field(default=None, max_length=20_000)
    webhook_url: str | None = None
    scheduled_at: datetime | None = None
    status: CampaignStatus | None = None


class CampaignResponse(BaseModel):
    id: int
    name: str
    description: str | None
    voice_profile_id: int
    message_template: str
    status: CampaignStatus
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    total_recipients: int
    delivered: int
    failed: int
    webhook_url: str | None
    created_by_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class CampaignProgress(BaseModel):
    campaign_id: int
    status: CampaignStatus
    total_recipients: int
    delivered: int
    failed: int
    pending: int
    calling: int
    skipped: int
    dnc_blocked: int
    percent_complete: float


class TwilioStatusForm(BaseModel):
    """Twilio status callback (form-urlencoded) — optional fields for flexibility."""

    CallSid: str | None = None
    CallStatus: str | None = None
    CallDuration: str | None = None
    To: str | None = None
    From: str | None = None
    AnsweredBy: str | None = None

    model_config = {"extra": "allow"}
