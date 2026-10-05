from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser
from app.services.voice_crew import VoiceCrew
from app.tasks.crew_tasks import run_voice_crew_task

router = APIRouter()


class VoiceCrewRequest(BaseModel):
    purpose: str = Field(..., min_length=3, max_length=500)
    patient_name: str = Field(default="there", max_length=80)
    when: str = Field(default="tomorrow", max_length=80)
    async_run: bool = False


class VoiceCrewResponse(BaseModel):
    crew: str
    used_llm: bool
    intent: str
    script: str
    steps: list[dict[str, Any]]
    task_id: str | None = None


@router.post("/script", response_model=VoiceCrewResponse)
async def run_voice_crew(body: VoiceCrewRequest, _: CurrentUser) -> VoiceCrewResponse:
    if body.async_run:
        task = run_voice_crew_task.delay(body.purpose, body.patient_name, body.when)
        return VoiceCrewResponse(
            crew="voice",
            used_llm=False,
            intent="queued",
            script="queued",
            steps=[],
            task_id=task.id,
        )
    result = VoiceCrew().run(body.purpose, body.patient_name, body.when)
    return VoiceCrewResponse(
        crew=result.crew,
        used_llm=result.used_llm,
        intent=result.intent,
        script=result.script,
        steps=result.steps,
    )
