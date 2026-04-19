"""User model with RBAC and optional API key."""

import enum
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), default=UserRole.VIEWER)
    api_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    voice_profiles: Mapped[list["VoiceProfile"]] = relationship(back_populates="creator", foreign_keys="VoiceProfile.created_by_id")
    tts_jobs: Mapped[list["TTSJob"]] = relationship(back_populates="creator", foreign_keys="TTSJob.created_by_id")
    campaigns: Mapped[list["Campaign"]] = relationship(back_populates="creator", foreign_keys="Campaign.created_by_id")
    dnc_entries: Mapped[list["DNCEntry"]] = relationship(back_populates="added_by_user", foreign_keys="DNCEntry.added_by_id")
    usage_records: Mapped[list["UsageRecord"]] = relationship(back_populates="user")


# Forward refs for type checkers
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.voice import Campaign, DNCEntry, TTSJob, UsageRecord, VoiceProfile
