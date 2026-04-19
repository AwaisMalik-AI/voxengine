"""Voice profiles, TTS jobs, campaigns, DNC, usage, webhooks."""

import enum
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TTSJobStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class CampaignStatus(str, enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RecipientStatus(str, enum.Enum):
    PENDING = "pending"
    CALLING = "calling"
    DELIVERED = "delivered"
    FAILED = "failed"
    SKIPPED = "skipped"
    DNC_BLOCKED = "dnc_blocked"


class UsageAction(str, enum.Enum):
    TTS_GENERATE = "tts_generate"
    CAMPAIGN_CALL = "campaign_call"
    API_CALL = "api_call"


class WebhookStatus(str, enum.Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class VoiceProfile(Base):
    __tablename__ = "voice_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    language: Mapped[str] = mapped_column(String(32), default="en-US")
    gender: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tts_engine: Mapped[str] = mapped_column(String(32), nullable=False)  # edge_tts | openai
    voice_id_external: Mapped[str] = mapped_column(String(256), nullable=False)
    sample_audio_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    creator: Mapped["User"] = relationship(back_populates="voice_profiles", foreign_keys=[created_by_id])
    tts_jobs: Mapped[list["TTSJob"]] = relationship(back_populates="voice_profile")
    campaigns: Mapped[list["Campaign"]] = relationship(back_populates="voice_profile")


class TTSJob(Base):
    __tablename__ = "tts_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    voice_profile_id: Mapped[int] = mapped_column(ForeignKey("voice_profiles.id"), nullable=False)
    output_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[TTSJobStatus] = mapped_column(Enum(TTSJobStatus, name="tts_job_status"), default=TTSJobStatus.QUEUED)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    voice_profile: Mapped["VoiceProfile"] = relationship(back_populates="tts_jobs")
    creator: Mapped["User"] = relationship(back_populates="tts_jobs", foreign_keys=[created_by_id])


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    voice_profile_id: Mapped[int] = mapped_column(ForeignKey("voice_profiles.id"), nullable=False)
    message_template: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus, name="campaign_status"),
        default=CampaignStatus.DRAFT,
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_recipients: Mapped[int] = mapped_column(Integer, default=0)
    delivered: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    webhook_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    voice_profile: Mapped["VoiceProfile"] = relationship(back_populates="campaigns")
    creator: Mapped["User"] = relationship(back_populates="campaigns", foreign_keys=[created_by_id])
    recipients: Mapped[list["CampaignRecipient"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")
    webhook_deliveries: Mapped[list["WebhookDelivery"]] = relationship(back_populates="campaign")


class CampaignRecipient(Base):
    __tablename__ = "campaign_recipients"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    variables: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[RecipientStatus] = mapped_column(
        Enum(RecipientStatus, name="recipient_status"),
        default=RecipientStatus.PENDING,
    )
    call_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    twilio_call_sid: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    campaign: Mapped["Campaign"] = relationship(back_populates="recipients")


class DNCEntry(Base):
    __tablename__ = "dnc_entries"
    __table_args__ = (UniqueConstraint("phone_number", name="uq_dnc_phone"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    added_by_user: Mapped["User"] = relationship(back_populates="dnc_entries", foreign_keys=[added_by_id])


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    action: Mapped[UsageAction] = mapped_column(Enum(UsageAction, name="usage_action"), nullable=False)
    characters_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    credits_used: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)

    user: Mapped["User"] = relationship(back_populates="usage_records")


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[WebhookStatus] = mapped_column(
        Enum(WebhookStatus, name="webhook_delivery_status"),
        default=WebhookStatus.PENDING,
    )
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    campaign: Mapped["Campaign | None"] = relationship(back_populates="webhook_deliveries")


from app.models.user import User  # noqa: E402  # circular import resolution
