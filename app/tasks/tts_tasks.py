"""Background tasks: TTS generation, campaign calls, webhook delivery."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

import aiofiles
import httpx

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.voice import (
    Campaign,
    CampaignRecipient,
    RecipientStatus,
    TTSJob,
    TTSJobStatus,
    UsageAction,
    VoiceProfile,
    WebhookDelivery,
    WebhookStatus,
)
from app.services.campaign_manager import CampaignManager, render_message_template
from app.services.telephony import TelephonyService
from app.services.tts_engine import TTSEngine
from app.services.usage_tracker import UsageTracker
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _generate_tts_async(job_id: int) -> None:
    async with AsyncSessionLocal() as session:
        job = await session.get(TTSJob, job_id)
        if not job:
            return
        try:
            vp = await session.get(VoiceProfile, job.voice_profile_id)
            if not vp:
                job.status = TTSJobStatus.FAILED
                job.error_message = "Voice profile missing"
                await session.commit()
                return
            job.status = TTSJobStatus.PROCESSING
            await session.flush()
            tts = TTSEngine()
            audio, elapsed_ms = await tts.generate_with_timing(job.text, vp)
            out_dir = Path(settings.STORAGE_PATH) / "tts"
            out_dir.mkdir(parents=True, exist_ok=True)
            fname = f"{job.id}_{uuid.uuid4().hex}.mp3"
            out_path = out_dir / fname
            async with aiofiles.open(out_path, "wb") as f:
                await f.write(audio)
            job.output_path = f"tts/{fname}"
            job.status = TTSJobStatus.COMPLETED
            job.processing_time_ms = elapsed_ms
            job.file_size_bytes = len(audio)
            job.duration_seconds = tts.estimate_duration(job.text)
            await UsageTracker(session).record_usage(
                job.created_by_id,
                UsageAction.TTS_GENERATE,
                characters=len(job.text),
                credits=max(len(job.text) * 0.001, 0.01),
            )
            await session.commit()
        except Exception as e:  # noqa: BLE001
            logger.exception("TTS job %s failed", job_id)
            await session.rollback()
            async with AsyncSessionLocal() as session2:
                j2 = await session2.get(TTSJob, job_id)
                if j2:
                    j2.status = TTSJobStatus.FAILED
                    j2.error_message = str(e)[:2000]
                    await session2.commit()


@celery_app.task(name="app.tasks.tts_tasks.generate_tts_task", bind=True, max_retries=3)
def generate_tts_task(self, job_id: int) -> None:
    try:
        asyncio.run(_generate_tts_async(job_id))
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc, countdown=30) from exc


async def _campaign_call_async(recipient_id: int) -> None:
    async with AsyncSessionLocal() as session:
        recipient = await session.get(CampaignRecipient, recipient_id)
        if not recipient or recipient.status != RecipientStatus.PENDING:
            return
        camp = await session.get(Campaign, recipient.campaign_id)
        if not camp:
            return
        vp = await session.get(VoiceProfile, camp.voice_profile_id)
        if not vp:
            recipient.status = RecipientStatus.FAILED
            recipient.error_message = "Voice profile missing"
            await session.commit()
            return

        mgr = CampaignManager(session)
        if settings.DNC_ENABLED and await mgr.check_dnc(recipient.phone_number):
            recipient.status = RecipientStatus.DNC_BLOCKED
            await session.commit()
            return

        ctx = {
            "name": recipient.name or "",
            "phone_number": recipient.phone_number,
            **(recipient.variables or {}),
        }
        text = render_message_template(camp.message_template, ctx)
        tts = TTSEngine()
        try:
            audio, _elapsed_ms = await tts.generate_with_timing(text, vp)
        except Exception as e:  # noqa: BLE001
            recipient.status = RecipientStatus.FAILED
            recipient.error_message = str(e)[:2000]
            await session.commit()
            return

        out_dir = Path(settings.STORAGE_PATH) / "campaigns" / str(camp.id)
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = f"recipient_{recipient.id}_{uuid.uuid4().hex}.mp3"
        out_path = out_dir / fname
        async with aiofiles.open(out_path, "wb") as f:
            await f.write(audio)
        rel = f"campaigns/{camp.id}/{fname}"
        public_url = f"{settings.PUBLIC_BASE_URL.rstrip('/')}/storage/{rel}"

        recipient.attempted_at = datetime.now(UTC)
        await session.flush()

        telephony = TelephonyService(session)
        try:
            result = await telephony.place_call(recipient.phone_number, public_url, camp.id, recipient.id)
        except Exception as e:  # noqa: BLE001
            recipient.status = RecipientStatus.FAILED
            recipient.error_message = str(e)[:2000]
            await session.commit()
            return

        if result.get("simulated"):
            recipient.status = RecipientStatus.DELIVERED
            recipient.call_duration_seconds = tts.estimate_duration(text)
            camp.delivered = (camp.delivered or 0) + 1

        await UsageTracker(session).record_usage(
            camp.created_by_id,
            UsageAction.CAMPAIGN_CALL,
            characters=len(text),
            duration=recipient.call_duration_seconds,
            credits=max((recipient.call_duration_seconds or 0) * 0.05, 0.1),
        )

        if camp.webhook_url and recipient.status == RecipientStatus.DELIVERED:
            payload = {
                "event": "call.completed",
                "campaign_id": camp.id,
                "recipient_id": recipient.id,
                "phone_number": recipient.phone_number,
                "simulated": bool(result.get("simulated")),
            }
            wd = WebhookDelivery(
                campaign_id=camp.id,
                url=camp.webhook_url,
                payload=payload,
                status=WebhookStatus.PENDING,
            )
            session.add(wd)
            await session.flush()
            deliver_webhook_task.apply_async(args=[wd.id], queue="webhooks")

        await session.commit()


@celery_app.task(name="app.tasks.tts_tasks.campaign_call_task", bind=True, max_retries=3)
def campaign_call_task(self, recipient_id: int) -> None:
    try:
        asyncio.run(_campaign_call_async(recipient_id))
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc, countdown=60) from exc


async def _deliver_webhook_async(delivery_id: int) -> None:
    async with AsyncSessionLocal() as session:
        wd = await session.get(WebhookDelivery, delivery_id)
        if not wd:
            return
        wd.attempts = (wd.attempts or 0) + 1
        try:
            async with httpx.AsyncClient(timeout=float(settings.WEBHOOK_TIMEOUT)) as client:
                r = await client.post(wd.url, json=wd.payload)
            wd.response_code = r.status_code
            if 200 <= r.status_code < 300:
                wd.status = WebhookStatus.DELIVERED
            else:
                wd.status = WebhookStatus.FAILED
        except Exception as e:  # noqa: BLE001
            wd.status = WebhookStatus.FAILED
            wd.response_code = None
            logger.warning("Webhook %s failed: %s", delivery_id, e)
        await session.commit()


@celery_app.task(name="app.tasks.tts_tasks.deliver_webhook_task", bind=True, max_retries=5)
def deliver_webhook_task(self, delivery_id: int) -> None:
    try:
        asyncio.run(_deliver_webhook_async(delivery_id))
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc, countdown=120) from exc
