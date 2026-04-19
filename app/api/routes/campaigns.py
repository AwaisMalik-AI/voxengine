"""Campaigns, recipients, Twilio callbacks, TwiML."""

from urllib.parse import unquote
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, OperatorUser
from app.models.voice import Campaign, CampaignRecipient, CampaignStatus, UsageAction, VoiceProfile
from app.schemas.campaigns import (
    CampaignCreate,
    CampaignProgress,
    CampaignRecipientBulk,
    CampaignRecipientResponse,
    CampaignResponse,
    CampaignUpdate,
)
from app.services.campaign_manager import CampaignManager
from app.services.telephony import TelephonyService
from app.services.usage_tracker import UsageTracker

router = APIRouter()


@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(body: CampaignCreate, db: DbSession, user: OperatorUser) -> Campaign:
    vp = await db.get(VoiceProfile, body.voice_profile_id)
    if not vp or vp.created_by_id != user.id:
        raise HTTPException(status_code=404, detail="Voice profile not found")
    mgr = CampaignManager(db)
    recipients_data = None
    if body.recipients:
        recipients_data = [r.model_dump() for r in body.recipients]
    camp = await mgr.create_campaign(
        name=body.name,
        description=body.description,
        voice_profile_id=body.voice_profile_id,
        message_template=body.message_template,
        webhook_url=body.webhook_url,
        scheduled_at=body.scheduled_at,
        created_by_id=user.id,
        recipients_data=recipients_data,
    )
    await UsageTracker(db).record_usage(user.id, UsageAction.API_CALL)
    return camp


@router.get("", response_model=list[CampaignResponse])
async def list_campaigns(db: DbSession, user: CurrentUser) -> list[Campaign]:
    q = select(Campaign).where(Campaign.created_by_id == user.id).order_by(Campaign.created_at.desc())
    return list((await db.execute(q)).scalars().all())


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(campaign_id: int, db: DbSession, user: CurrentUser) -> Campaign:
    c = await db.get(Campaign, campaign_id)
    if not c or c.created_by_id != user.id:
        raise HTTPException(404, detail="Campaign not found")
    return c


@router.patch("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: int, body: CampaignUpdate, db: DbSession, user: OperatorUser
) -> Campaign:
    c = await db.get(Campaign, campaign_id)
    if not c or c.created_by_id != user.id:
        raise HTTPException(404, detail="Campaign not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    await db.flush()
    await db.refresh(c)
    return c


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(campaign_id: int, db: DbSession, user: OperatorUser) -> None:
    c = await db.get(Campaign, campaign_id)
    if not c or c.created_by_id != user.id:
        raise HTTPException(404, detail="Campaign not found")
    if c.status == CampaignStatus.RUNNING:
        raise HTTPException(400, detail="Stop or pause campaign before delete")
    await db.delete(c)


@router.post("/{campaign_id}/start", response_model=CampaignResponse)
async def start_campaign_route(campaign_id: int, db: DbSession, user: OperatorUser) -> Campaign:
    c = await db.get(Campaign, campaign_id)
    if not c or c.created_by_id != user.id:
        raise HTTPException(404, detail="Campaign not found")
    mgr = CampaignManager(db)
    try:
        camp = await mgr.start_campaign(campaign_id)
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e
    await UsageTracker(db).record_usage(user.id, UsageAction.API_CALL)
    return camp


@router.post("/{campaign_id}/pause", response_model=CampaignResponse)
async def pause_campaign_route(campaign_id: int, db: DbSession, user: OperatorUser) -> Campaign:
    c = await db.get(Campaign, campaign_id)
    if not c or c.created_by_id != user.id:
        raise HTTPException(404, detail="Campaign not found")
    mgr = CampaignManager(db)
    try:
        camp = await mgr.pause_campaign(campaign_id)
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e
    return camp


@router.get("/{campaign_id}/progress", response_model=CampaignProgress)
async def campaign_progress(campaign_id: int, db: DbSession, user: CurrentUser) -> CampaignProgress:
    c = await db.get(Campaign, campaign_id)
    if not c or c.created_by_id != user.id:
        raise HTTPException(404, detail="Campaign not found")
    mgr = CampaignManager(db)
    try:
        p = await mgr.get_campaign_progress(campaign_id)
    except ValueError as e:
        raise HTTPException(404, detail=str(e)) from e
    return CampaignProgress(**p)


@router.post("/{campaign_id}/recipients", status_code=status.HTTP_201_CREATED)
async def bulk_add_recipients(
    campaign_id: int, body: CampaignRecipientBulk, db: DbSession, user: OperatorUser
) -> dict:
    c = await db.get(Campaign, campaign_id)
    if not c or c.created_by_id != user.id:
        raise HTTPException(404, detail="Campaign not found")
    mgr = CampaignManager(db)
    try:
        n = await mgr.add_recipients_bulk(campaign_id, [r.model_dump() for r in body.recipients])
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e
    return {"added": n}


@router.get("/{campaign_id}/recipients", response_model=list[CampaignRecipientResponse])
async def list_recipients(
    campaign_id: int,
    db: DbSession,
    user: CurrentUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> list[CampaignRecipient]:
    c = await db.get(Campaign, campaign_id)
    if not c or c.created_by_id != user.id:
        raise HTTPException(404, detail="Campaign not found")
    q = (
        select(CampaignRecipient)
        .where(CampaignRecipient.campaign_id == campaign_id)
        .order_by(CampaignRecipient.id)
        .offset(skip)
        .limit(limit)
    )
    return list((await db.execute(q)).scalars().all())


@router.api_route("/webhook-callback/twilio", methods=["GET", "POST"])
async def twilio_status_webhook(request: Request, db: DbSession) -> dict:
    """Twilio status callback (validate Twilio signature in production)."""
    if request.method == "POST":
        form = await request.form()
        data = {str(k): str(v) for k, v in form.items()}
    else:
        data = dict(request.query_params)
    svc = TelephonyService(db)
    await svc.handle_status_callback(data)
    return {"ok": True}


@router.get("/twiml/voice")
async def twilio_twiml_voice(media_url: str) -> Response:
    decoded = unquote(media_url)
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    allowed = f"{base}/storage/"
    if not decoded.startswith(allowed):
        raise HTTPException(status_code=400, detail="Invalid media_url for TwiML")
    safe = escape(decoded)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Play>{safe}</Play></Response>'
    return Response(content=xml, media_type="application/xml")
