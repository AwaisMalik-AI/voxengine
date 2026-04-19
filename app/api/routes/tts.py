"""TTS generation and job tracking."""

import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, OperatorUser
from app.models.voice import TTSJob, TTSJobStatus, VoiceProfile
from app.schemas.tts import TTSGenerateRequest, TTSJobListResponse, TTSJobResponse
from app.services.tts_engine import TTSEngine
from app.services.usage_tracker import UsageTracker
from app.models.voice import UsageAction

router = APIRouter()


@router.post("/generate", response_model=TTSJobResponse, status_code=status.HTTP_201_CREATED)
async def generate_tts(body: TTSGenerateRequest, db: DbSession, user: OperatorUser) -> TTSJob:
    vp = await db.get(VoiceProfile, body.voice_profile_id)
    if not vp or vp.created_by_id != user.id:
        raise HTTPException(status_code=404, detail="Voice profile not found")

    job = TTSJob(
        text=body.text,
        voice_profile_id=vp.id,
        status=TTSJobStatus.QUEUED,
        created_by_id=user.id,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)

    if body.async_job:
        from app.tasks.tts_tasks import generate_tts_task

        generate_tts_task.apply_async(args=[job.id], queue="tts")
        return job

    tts = TTSEngine()
    job.status = TTSJobStatus.PROCESSING
    await db.flush()
    try:
        audio, elapsed_ms = await tts.generate_with_timing(body.text, vp)
        out_dir = Path(settings.STORAGE_PATH) / "tts"
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{job.id}_{uuid.uuid4().hex}.mp3"
        out_path = out_dir / fname
        async with aiofiles.open(out_path, "wb") as f:
            await f.write(audio)
        rel = f"tts/{fname}"
        job.output_path = rel
        job.status = TTSJobStatus.COMPLETED
        job.processing_time_ms = elapsed_ms
        job.file_size_bytes = len(audio)
        job.duration_seconds = tts.estimate_duration(body.text)
    except Exception as e:  # noqa: BLE001
        job.status = TTSJobStatus.FAILED
        job.error_message = str(e)[:2000]
    await db.flush()
    await db.refresh(job)
    await UsageTracker(db).record_usage(
        user.id,
        UsageAction.TTS_GENERATE,
        characters=len(body.text),
        credits=max(len(body.text) * 0.001, 0.01),
    )
    return job


@router.get("/jobs", response_model=TTSJobListResponse)
async def list_tts_jobs(
    db: DbSession,
    user: CurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> TTSJobListResponse:
    q = select(TTSJob).where(TTSJob.created_by_id == user.id).order_by(TTSJob.created_at.desc())
    count_q = select(func.count()).select_from(TTSJob).where(TTSJob.created_by_id == user.id)
    total = int((await db.execute(count_q)).scalar_one())
    q = q.offset(skip).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return TTSJobListResponse(
        items=[TTSJobResponse.model_validate(r) for r in rows],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/jobs/{job_id}", response_model=TTSJobResponse)
async def get_tts_job(job_id: int, db: DbSession, user: CurrentUser) -> TTSJob:
    job = await db.get(TTSJob, job_id)
    if not job or job.created_by_id != user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs/{job_id}/audio")
async def download_tts_audio(job_id: int, db: DbSession, user: CurrentUser) -> Response:
    job = await db.get(TTSJob, job_id)
    if not job or job.created_by_id != user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.output_path or job.status != TTSJobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Audio not available")
    path = Path(settings.STORAGE_PATH) / job.output_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File missing on disk")
    async with aiofiles.open(path, "rb") as f:
        data = await f.read()
    return Response(content=data, media_type="audio/mpeg", headers={"Content-Disposition": f'attachment; filename="{job_id}.mp3"'})
