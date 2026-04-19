"""Campaign lifecycle: create, start, pause, progress, DNC."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.voice import (
    Campaign,
    CampaignRecipient,
    CampaignStatus,
    DNCEntry,
    RecipientStatus,
    VoiceProfile,
)


def render_message_template(template: str, ctx: dict[str, Any]) -> str:
    """Replace {{ key }} placeholders with values from ctx."""

    def repl(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        if key in ctx:
            return str(ctx[key])
        return match.group(0)

    return re.sub(r"\{\{\s*([^}]+?)\s*\}\}", repl, template)


class CampaignManager:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_campaign(
        self,
        *,
        name: str,
        description: str | None,
        voice_profile_id: int,
        message_template: str,
        webhook_url: str | None,
        scheduled_at: datetime | None,
        created_by_id: int,
        recipients_data: list[dict[str, Any]] | None = None,
    ) -> Campaign:
        vp = await self.db.get(VoiceProfile, voice_profile_id)
        if not vp:
            raise ValueError("Voice profile not found")

        status = CampaignStatus.SCHEDULED if scheduled_at else CampaignStatus.DRAFT
        campaign = Campaign(
            name=name,
            description=description,
            voice_profile_id=voice_profile_id,
            message_template=message_template,
            status=status,
            scheduled_at=scheduled_at,
            webhook_url=webhook_url,
            created_by_id=created_by_id,
            total_recipients=0,
        )
        self.db.add(campaign)
        await self.db.flush()

        if recipients_data:
            await self._add_recipients(campaign.id, recipients_data)

        await self.db.refresh(campaign)
        return campaign

    async def _add_recipients(self, campaign_id: int, recipients_data: list[dict[str, Any]]) -> int:
        count = 0
        for row in recipients_data:
            phone = row["phone_number"]
            if settings.DNC_ENABLED and await self.check_dnc(phone):
                rec = CampaignRecipient(
                    campaign_id=campaign_id,
                    phone_number=phone,
                    name=row.get("name"),
                    variables=row.get("variables"),
                    status=RecipientStatus.DNC_BLOCKED,
                )
            else:
                rec = CampaignRecipient(
                    campaign_id=campaign_id,
                    phone_number=phone,
                    name=row.get("name"),
                    variables=row.get("variables"),
                    status=RecipientStatus.PENDING,
                )
            self.db.add(rec)
            count += 1
        await self.db.flush()
        total_res = await self.db.execute(
            select(func.count()).select_from(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign_id)
        )
        total = int(total_res.scalar_one())
        await self.db.execute(update(Campaign).where(Campaign.id == campaign_id).values(total_recipients=total))
        return count

    async def add_recipients_bulk(self, campaign_id: int, recipients_data: list[dict[str, Any]]) -> int:
        camp = await self.db.get(Campaign, campaign_id)
        if not camp:
            raise ValueError("Campaign not found")
        if camp.status not in (CampaignStatus.DRAFT, CampaignStatus.PAUSED, CampaignStatus.SCHEDULED):
            raise ValueError("Cannot add recipients to campaign in current status")
        return await self._add_recipients(campaign_id, recipients_data)

    async def start_campaign(self, campaign_id: int) -> Campaign:
        camp = await self.db.get(Campaign, campaign_id, options=[selectinload(Campaign.recipients)])
        if not camp:
            raise ValueError("Campaign not found")
        if camp.status in (CampaignStatus.RUNNING, CampaignStatus.COMPLETED, CampaignStatus.CANCELLED):
            raise ValueError("Campaign cannot be started from this status")

        now = datetime.now(UTC)
        await self.db.execute(
            update(Campaign)
            .where(Campaign.id == campaign_id)
            .values(status=CampaignStatus.RUNNING, started_at=now)
        )
        await self.db.commit()
        camp = await self.db.get(Campaign, campaign_id, options=[selectinload(Campaign.recipients)])
        assert camp

        from app.tasks.tts_tasks import campaign_call_task

        for recipient in camp.recipients:
            if recipient.status == RecipientStatus.PENDING:
                campaign_call_task.apply_async(args=[recipient.id], queue="calls")

        return camp

    async def pause_campaign(self, campaign_id: int) -> Campaign:
        camp = await self.db.get(Campaign, campaign_id)
        if not camp:
            raise ValueError("Campaign not found")
        if camp.status != CampaignStatus.RUNNING:
            raise ValueError("Only running campaigns can be paused")
        camp.status = CampaignStatus.PAUSED
        await self.db.flush()
        await self.db.refresh(camp)
        return camp

    async def get_campaign_progress(self, campaign_id: int) -> dict[str, Any]:
        camp = await self.db.get(Campaign, campaign_id)
        if not camp:
            raise ValueError("Campaign not found")

        q = (
            select(CampaignRecipient.status, func.count())
            .where(CampaignRecipient.campaign_id == campaign_id)
            .group_by(CampaignRecipient.status)
        )
        rows = (await self.db.execute(q)).all()
        counts: dict[str, int] = {s.value: 0 for s in RecipientStatus}
        for st, c in rows:
            counts[st.value] = int(c)

        total = camp.total_recipients or sum(counts.values())
        done = counts["delivered"] + counts["failed"] + counts["skipped"] + counts["dnc_blocked"]
        pct = round(100.0 * done / total, 2) if total else 0.0

        return {
            "campaign_id": campaign_id,
            "status": camp.status,
            "total_recipients": total,
            "delivered": camp.delivered,
            "failed": camp.failed,
            "pending": counts["pending"],
            "calling": counts["calling"],
            "skipped": counts["skipped"],
            "dnc_blocked": counts["dnc_blocked"],
            "percent_complete": pct,
        }

    async def check_dnc(self, phone_number: str) -> bool:
        if not settings.DNC_ENABLED:
            return False
        q = select(DNCEntry.id).where(DNCEntry.phone_number == phone_number).limit(1)
        return (await self.db.execute(q)).scalar_one_or_none() is not None
