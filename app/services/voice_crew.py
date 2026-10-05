"""Voice campaign crew: intent → scriptwriter → compliance."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings


@dataclass
class CrewResult:
    crew: str = "voice"
    used_llm: bool = False
    intent: str = "reminder"
    script: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)


def _llm(system: str, user: str) -> str | None:
    key = settings.OPENAI_API_KEY
    if not key:
        return None
    try:
        with httpx.Client(timeout=45.0) as client:
            resp = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-4o-mini",
                    "temperature": 0.3,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
    except Exception:
        return None


class VoiceCrew:
    def run(self, purpose: str, patient_name: str = "there", when: str = "tomorrow") -> CrewResult:
        intent = _llm(
            "Classify voice-call intent in one word: reminder|confirm|reschedule|cancel.",
            purpose,
        ) or ("reminder" if "remind" in purpose.lower() else "confirm")
        script = _llm(
            "Write a 20-second healthcare reminder. Calm, no diagnosis, include opt-out.",
            f"Name={patient_name} When={when} Purpose={purpose} Intent={intent}",
        ) or (
            f"Hello {patient_name}, this is a reminder about your appointment {when}. "
            f"{purpose.strip()} Press 1 to confirm or 9 to stop these calls."
        )
        compliance = _llm(
            "Compliance reviewer for healthcare voice outreach. Check DNC, PHI, and consent.",
            script,
        ) or "Compliance: no PHI in voicemail, honor DNC, keep under 30 seconds, offer opt-out."
        return CrewResult(
            used_llm=bool(settings.OPENAI_API_KEY),
            intent=intent.strip().split()[0].lower(),
            script=script,
            steps=[
                {"agent": "intent", "output": intent},
                {"agent": "scriptwriter", "output": script},
                {"agent": "compliance", "output": compliance},
            ],
        )
