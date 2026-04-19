"""Application settings loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    APP_NAME: str = "VoxEngine"
    DEBUG: bool = False
    API_PREFIX: str = "/api"

    # Database
    DATABASE_URL: str = Field(
        ...,
        description="Async PostgreSQL URL, e.g. postgresql+asyncpg://user:pass@host:5432/db",
    )

    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # Security
    SECRET_KEY: str = Field(..., min_length=32, description="JWT signing secret")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    API_KEY_PREFIX: str = "vx_"

    # TTS
    TTS_ENGINE: Literal["edge_tts", "openai"] = "edge_tts"
    OPENAI_API_KEY: str | None = None
    OPENAI_TTS_MODEL: str = "tts-1"
    OPENAI_TTS_VOICE: str = "alloy"

    # Celery
    CELERY_BROKER_URL: str | None = None
    CELERY_RESULT_BACKEND: str | None = None

    @property
    def celery_broker(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL

    @property
    def celery_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL

    # Storage
    STORAGE_PATH: str = Field(default="./storage")

    # Twilio (optional)
    TWILIO_ACCOUNT_SID: str | None = None
    TWILIO_AUTH_TOKEN: str | None = None
    TWILIO_PHONE_NUMBER: str | None = None
    PUBLIC_BASE_URL: str = Field(
        default="http://localhost:8000",
        description="Public URL for Twilio callbacks (audio URLs, status webhooks)",
    )

    # Limits
    MAX_CONCURRENT_CALLS: int = 10
    DNC_ENABLED: bool = True
    WEBHOOK_TIMEOUT: int = 30
    RATE_LIMIT_PER_MINUTE: int = 120

    # Usage / quotas
    DEFAULT_MONTHLY_CREDIT_QUOTA: float = 10_000.0

    @field_validator("DATABASE_URL")
    @classmethod
    def require_async_driver(cls, v: str) -> str:
        if "+asyncpg" not in v and "postgresql+asyncpg" not in v:
            if v.startswith("postgresql://"):
                return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
