"""Do-not-call list management."""

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import AdminUser, CurrentUser, DbSession, OperatorUser
from app.models.voice import DNCEntry
from app.schemas.dnc import DNCEntryCreate, DNCEntryResponse, DNCCheckRequest, DNCCheckResponse
from app.services.campaign_manager import CampaignManager
from app.services.usage_tracker import UsageTracker
from app.models.voice import UsageAction

router = APIRouter()


@router.post("", response_model=DNCEntryResponse, status_code=status.HTTP_201_CREATED)
async def add_dnc(body: DNCEntryCreate, db: DbSession, user: OperatorUser) -> DNCEntry:
    if not settings.DNC_ENABLED:
        raise HTTPException(status_code=400, detail="DNC is disabled")
    existing = await db.execute(select(DNCEntry).where(DNCEntry.phone_number == body.phone_number))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Number already on DNC list")
    entry = DNCEntry(phone_number=body.phone_number, reason=body.reason, added_by_id=user.id)
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    await UsageTracker(db).record_usage(user.id, UsageAction.API_CALL)
    return entry


@router.get("", response_model=list[DNCEntryResponse])
async def list_dnc(
    db: DbSession,
    user: CurrentUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> list[DNCEntry]:
    q = select(DNCEntry).order_by(DNCEntry.created_at.desc()).offset(skip).limit(limit)
    return list((await db.execute(q)).scalars().all())


@router.delete("/{phone:path}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_dnc(phone: str, db: DbSession, user: AdminUser) -> None:
    result = await db.execute(select(DNCEntry).where(DNCEntry.phone_number == phone))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Not on DNC list")
    await db.delete(row)


@router.post("/check", response_model=DNCCheckResponse)
async def check_dnc(body: DNCCheckRequest, db: DbSession, user: CurrentUser) -> DNCCheckResponse:
    mgr = CampaignManager(db)
    on_list = await mgr.check_dnc(body.phone_number)
    await UsageTracker(db).record_usage(user.id, UsageAction.API_CALL)
    return DNCCheckResponse(phone_number=body.phone_number, on_dnc_list=on_list)
