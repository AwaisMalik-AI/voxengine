"""Voice profile CRUD, catalog, preview."""

import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, OperatorUser
from app.models.voice import UsageAction, VoiceProfile
from app.schemas.voices import (
    VoiceAvailableItem,
    VoicePreviewRequest,
    VoiceProfileCreate,
    VoiceProfileResponse,
    VoiceProfileUpdate,
)
from app.services.tts_engine import TTSEngine
from app.services.usage_tracker import UsageTracker

router = APIRouter()


@router.get("/catalog/available", response_model=list[VoiceAvailableItem])
async def list_available_voices(
    user: CurrentUser,
    engine: str | None = Query(default=None, description="edge_tts or openai"),
) -> list[dict]:
    eng = engine or settings.TTS_ENGINE
    if eng not in ("edge_tts", "openai"):
        raise HTTPException(status_code=400, detail="Invalid engine")
    tts = TTSEngine()
    return await tts.list_available_voices(engine=eng)  # type: ignore[arg-type]


@router.post("/preview", status_code=status.HTTP_201_CREATED)
async def preview_voice(body: VoicePreviewRequest, db: DbSession, user: OperatorUser) -> dict:
    tts = TTSEngine()
    if body.voice_profile_id:
        vp = await db.get(VoiceProfile, body.voice_profile_id)
        if not vp or vp.created_by_id != user.id:
            raise HTTPException(status_code=404, detail="Voice profile not found")
    else:
        eng = body.tts_engine or settings.TTS_ENGINE
        vid = body.voice_id_external or ("en-US-AriaNeural" if eng == "edge_tts" else settings.OPENAI_TTS_VOICE)
        vp = VoiceProfile(
            name="preview",
            language="en-US",
            tts_engine=eng,
            voice_id_external=vid,
            created_by_id=user.id,
        )
    audio, elapsed_ms = await tts.generate_with_timing(body.text, vp)
    out_dir = Path(settings.STORAGE_PATH) / "previews"
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{user.id}_{uuid.uuid4().hex}.mp3"
    out_path = out_dir / fname
    async with aiofiles.open(out_path, "wb") as f:
        await f.write(audio)
    public_path = f"/storage/previews/{fname}"
    await UsageTracker(db).record_usage(
        user.id,
        UsageAction.TTS_GENERATE,
        characters=len(body.text),
        credits=max(len(body.text) * 0.001, 0.01),
    )
    return {"sample_url": public_path, "processing_time_ms": elapsed_ms, "size_bytes": len(audio)}


@router.get("", response_model=list[VoiceProfileResponse])
async def list_voice_profiles(db: DbSession, user: CurrentUser) -> list[VoiceProfileResponse]:
    q = select(VoiceProfile).where(VoiceProfile.created_by_id == user.id).order_by(VoiceProfile.created_at.desc())
    rows = (await db.execute(q)).scalars().all()
    return [VoiceProfileResponse.model_validate(r) for r in rows]


@router.post("", response_model=VoiceProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_voice_profile(body: VoiceProfileCreate, db: DbSession, user: OperatorUser) -> VoiceProfile:
    if body.is_default:
        res = await db.execute(select(VoiceProfile).where(VoiceProfile.created_by_id == user.id))
        for o in res.scalars():
            o.is_default = False
    vp = VoiceProfile(
        name=body.name,
        language=body.language,
        gender=body.gender,
        tts_engine=body.tts_engine,
        voice_id_external=body.voice_id_external,
        is_default=body.is_default,
        created_by_id=user.id,
    )
    db.add(vp)
    await db.flush()
    await db.refresh(vp)
    await UsageTracker(db).record_usage(user.id, UsageAction.API_CALL)
    return vp


@router.get("/{profile_id}", response_model=VoiceProfileResponse)
async def get_voice_profile(profile_id: int, db: DbSession, user: CurrentUser) -> VoiceProfile:
    vp = await db.get(VoiceProfile, profile_id)
    if not vp or vp.created_by_id != user.id:
        raise HTTPException(status_code=404, detail="Voice profile not found")
    return vp


@router.patch("/{profile_id}", response_model=VoiceProfileResponse)
async def update_voice_profile(
    profile_id: int, body: VoiceProfileUpdate, db: DbSession, user: OperatorUser
) -> VoiceProfile:
    vp = await db.get(VoiceProfile, profile_id)
    if not vp or vp.created_by_id != user.id:
        raise HTTPException(status_code=404, detail="Voice profile not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("is_default"):
        res = await db.execute(select(VoiceProfile).where(VoiceProfile.created_by_id == user.id))
        for o in res.scalars():
            o.is_default = False
    for k, v in data.items():
        setattr(vp, k, v)
    await db.flush()
    await db.refresh(vp)
    return vp


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_voice_profile(profile_id: int, db: DbSession, user: OperatorUser) -> None:
    vp = await db.get(VoiceProfile, profile_id)
    if not vp or vp.created_by_id != user.id:
        raise HTTPException(status_code=404, detail="Voice profile not found")
    await db.delete(vp)
