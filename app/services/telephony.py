"""Twilio integration with simulated fallback when not configured."""

from __future__ import annotations

import logging
import uuid
from typing import Any
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.voice import Campaign, CampaignRecipient, RecipientStatus, WebhookDelivery, WebhookStatus

logger = logging.getLogger(__name__)


class TelephonyService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._client = None
        if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
            from twilio.rest import Client

            self._client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

    def is_configured(self) -> bool:
        return self._client is not None and bool(settings.TWILIO_PHONE_NUMBER)

    async def place_call(
        self,
        phone_number: str,
        audio_url: str,
        campaign_id: int,
        recipient_id: int,
    ) -> dict[str, Any]:
        recipient = await self.db.get(CampaignRecipient, recipient_id)
        if not recipient or recipient.campaign_id != campaign_id:
            raise ValueError("Recipient not found for campaign")

        if not self.is_configured():
            call_sid = f"SIM_{uuid.uuid4().hex[:24]}"
            logger.info(
                "Simulated outbound call (Twilio not configured): to=%s campaign=%s recipient=%s url=%s",
                phone_number,
                campaign_id,
                recipient_id,
                audio_url,
            )
            recipient.twilio_call_sid = call_sid
            recipient.status = RecipientStatus.CALLING
            await self.db.flush()
            return {"call_sid": call_sid, "simulated": True, "status": "queued"}

        assert self._client is not None
        from_number = settings.TWILIO_PHONE_NUMBER
        base = settings.PUBLIC_BASE_URL.rstrip("/")
        status_cb = f"{base}/api/campaigns/webhook-callback/twilio"
        resolved_audio = audio_url if audio_url.startswith("http") else f"{base}{audio_url}"
        twiml_url = f"{base}/api/campaigns/twiml/voice?media_url={quote(resolved_audio, safe='')}"
        call = self._client.calls.create(
            to=phone_number,
            from_=from_number,
            url=twiml_url,
            status_callback=status_cb,
            status_callback_event=["initiated", "ringing", "answered", "completed"],
            status_callback_method="POST",
        )
        recipient.twilio_call_sid = call.sid
        recipient.status = RecipientStatus.CALLING
        await self.db.flush()
        return {"call_sid": call.sid, "simulated": False, "status": call.status}

    async def get_call_status(self, call_sid: str) -> dict[str, Any]:
        if call_sid.startswith("SIM_"):
            return {"call_sid": call_sid, "status": "completed", "simulated": True}
        if not self._client:
            return {"call_sid": call_sid, "status": "unknown", "simulated": True}
        call = self._client.calls(call_sid).fetch()
        return {"call_sid": call_sid, "status": call.status, "duration": call.duration}

    async def handle_status_callback(self, data: dict[str, Any]) -> CampaignRecipient | None:
        call_sid = data.get("CallSid") or data.get("call_sid")
        if not call_sid:
            logger.warning("Twilio callback missing CallSid: %s", data)
            return None

        q = select(CampaignRecipient).where(CampaignRecipient.twilio_call_sid == call_sid)
        result = await self.db.execute(q)
        recipient = result.scalar_one_or_none()
        if not recipient:
            logger.warning("No recipient for CallSid %s", call_sid)
            return None

        status_raw = (data.get("CallStatus") or data.get("CallStatus".lower()) or "").lower()
        duration_raw = data.get("CallDuration") or data.get("CallDuration".lower()) or "0"
        try:
            duration = float(duration_raw)
        except (TypeError, ValueError):
            duration = 0.0

        terminal_fail = {"failed", "busy", "no-answer", "canceled", "cancelled"}

        if recipient.status in (RecipientStatus.DELIVERED, RecipientStatus.FAILED, RecipientStatus.SKIPPED):
            await self.db.flush()
            return recipient

        if status_raw == "completed" and duration > 0:
            recipient.status = RecipientStatus.DELIVERED
            recipient.call_duration_seconds = duration
            camp = await self.db.get(Campaign, recipient.campaign_id)
            if camp:
                camp.delivered = (camp.delivered or 0) + 1
                if camp.webhook_url:
                    wd = WebhookDelivery(
                        campaign_id=camp.id,
                        url=camp.webhook_url,
                        payload={
                            "event": "call.completed",
                            "campaign_id": camp.id,
                            "recipient_id": recipient.id,
                            "phone_number": recipient.phone_number,
                            "duration_seconds": duration,
                            "simulated": False,
                        },
                        status=WebhookStatus.PENDING,
                    )
                    self.db.add(wd)
                    await self.db.flush()
                    from app.tasks.tts_tasks import deliver_webhook_task

                    deliver_webhook_task.apply_async(args=[wd.id], queue="webhooks")
        elif status_raw in terminal_fail:
            recipient.status = RecipientStatus.FAILED
            recipient.error_message = status_raw
            camp = await self.db.get(Campaign, recipient.campaign_id)
            if camp:
                camp.failed = (camp.failed or 0) + 1

        await self.db.flush()
        return recipient
