"""Usage metering, aggregation, and quota checks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.models.voice import UsageAction, UsageRecord


Period = Literal["daily", "weekly", "monthly"]


class UsageTracker:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record_usage(
        self,
        user_id: int,
        action: UsageAction,
        *,
        characters: int | None = None,
        duration: float | None = None,
        credits: float | None = None,
    ) -> UsageRecord:
        if credits is None:
            credits = self._default_credits(action, characters, duration)
        rec = UsageRecord(
            user_id=user_id,
            action=action,
            characters_used=characters,
            duration_seconds=duration,
            credits_used=float(credits),
        )
        self.db.add(rec)
        await self.db.flush()
        await self.db.refresh(rec)
        return rec

    @staticmethod
    def _default_credits(action: UsageAction, characters: int | None, duration: float | None) -> float:
        if action == UsageAction.TTS_GENERATE and characters is not None:
            return max(float(characters) * 0.001, 0.01)
        if action == UsageAction.CAMPAIGN_CALL and duration is not None:
            return max(float(duration) * 0.05, 0.1)
        if action == UsageAction.API_CALL:
            return 0.01
        return 0.05

    def _period_start(self, period: Period) -> datetime:
        now = datetime.now(UTC)
        if period == "daily":
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        if period == "weekly":
            start = now - timedelta(days=now.weekday())
            return start.replace(hour=0, minute=0, second=0, microsecond=0)
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    async def get_usage_summary(self, user_id: int, period: Period) -> dict:
        start = self._period_start(period)
        q = select(
            func.coalesce(func.sum(UsageRecord.credits_used), 0.0),
            func.coalesce(func.sum(UsageRecord.characters_used), 0),
            func.coalesce(func.sum(UsageRecord.duration_seconds), 0.0),
        ).where(UsageRecord.user_id == user_id, UsageRecord.created_at >= start)
        total_credits, total_chars, total_dur = (await self.db.execute(q)).one()

        by_action_q = select(UsageRecord.action, func.sum(UsageRecord.credits_used)).where(
            UsageRecord.user_id == user_id, UsageRecord.created_at >= start
        ).group_by(UsageRecord.action)
        rows = (await self.db.execute(by_action_q)).all()
        by_action = {a.value: float(c or 0) for a, c in rows}

        return {
            "user_id": user_id,
            "period": period,
            "total_credits": float(total_credits or 0),
            "total_characters": int(total_chars or 0),
            "total_duration_seconds": float(total_dur or 0),
            "by_action": by_action,
        }

    async def check_quota(self, user_id: int) -> dict:
        """Monthly credit quota from settings (per-user override can extend User model later)."""
        start = self._period_start("monthly")
        q = select(func.coalesce(func.sum(UsageRecord.credits_used), 0.0)).where(
            UsageRecord.user_id == user_id, UsageRecord.created_at >= start
        )
        used = float((await self.db.execute(q)).scalar_one() or 0)
        quota = float(settings.DEFAULT_MONTHLY_CREDIT_QUOTA)
        return {
            "user_id": user_id,
            "quota_credits": quota,
            "used_credits": used,
            "remaining_credits": max(quota - used, 0.0),
            "exceeded": used >= quota,
        }
