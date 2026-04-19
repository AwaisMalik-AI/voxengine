"""Voice profile schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class VoiceProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    language: str = Field(default="en-US", max_length=32)
    gender: str | None = Field(default=None, max_length=32)
    tts_engine: Literal["edge_tts", "openai"] = "edge_tts"
    voice_id_external: str = Field(min_length=1, max_length=256)
    is_default: bool = False


class VoiceProfileUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    language: str | None = Field(default=None, max_length=32)
    gender: str | None = None
    tts_engine: Literal["edge_tts", "openai"] | None = None
    voice_id_external: str | None = Field(default=None, max_length=256)
    sample_audio_path: str | None = None
    is_default: bool | None = None


class VoiceProfileResponse(BaseModel):
    id: int
    name: str
    language: str
    gender: str | None
    tts_engine: str
    voice_id_external: str
    sample_audio_path: str | None
    is_default: bool
    created_by_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class VoiceAvailableItem(BaseModel):
    id: str
    name: str | None = None
    locale: str | None = None
    gender: str | None = None
    engine: str


class VoicePreviewRequest(BaseModel):
    text: str = Field(default="Hello, this is a voice preview for healthcare reminders.", max_length=5000)
    voice_profile_id: int | None = None
    tts_engine: Literal["edge_tts", "openai"] | None = None
    voice_id_external: str | None = None
