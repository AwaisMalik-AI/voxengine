"""Usage summary and history."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.core.deps import CurrentUser, DbSession
from app.models.voice import UsageRecord
from app.schemas.usage import UsageHistoryItem, UsageSummaryResponse
from app.services.usage_tracker import UsageTracker
from sqlalchemy import select

router = APIRouter()


@router.get("/summary", response_model=UsageSummaryResponse)
async def usage_summary(
    db: DbSession,
    user: CurrentUser,
    period: Literal["daily", "weekly", "monthly"] = "monthly",
) -> UsageSummaryResponse:
    tracker = UsageTracker(db)
    data = await tracker.get_usage_summary(user.id, period)
    quota = await tracker.check_quota(user.id)
    data["quota"] = quota
    return UsageSummaryResponse(**{k: v for k, v in data.items() if k in UsageSummaryResponse.model_fields})


@router.get("/history", response_model=list[UsageHistoryItem])
async def usage_history(
    db: DbSession,
    user: CurrentUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> list[UsageRecord]:
    q = (
        select(UsageRecord)
        .where(UsageRecord.user_id == user.id)
        .order_by(UsageRecord.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list((await db.execute(q)).scalars().all())
