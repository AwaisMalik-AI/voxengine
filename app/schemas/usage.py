"""Usage metering schemas."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.voice import UsageAction


class UsageSummaryResponse(BaseModel):
    user_id: int
    period: str = Field(description="daily | weekly | monthly")
    total_credits: float
    total_characters: int
    total_duration_seconds: float
    by_action: dict[str, float]


class UsageHistoryItem(BaseModel):
    id: int
    action: UsageAction
    characters_used: int | None
    duration_seconds: float | None
    credits_used: float
    created_at: datetime

    model_config = {"from_attributes": True}
