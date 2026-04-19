"""TTS job schemas."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.voice import TTSJobStatus


class TTSGenerateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=50_000)
    voice_profile_id: int
    async_job: bool = Field(default=False, description="If true, queue Celery job and return job id")


class TTSJobResponse(BaseModel):
    id: int
    text: str
    voice_profile_id: int
    output_path: str | None
    status: TTSJobStatus
    duration_seconds: float | None
    file_size_bytes: int | None
    processing_time_ms: int | None
    error_message: str | None
    created_by_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class TTSJobListResponse(BaseModel):
    items: list[TTSJobResponse]
    total: int
    skip: int
    limit: int
