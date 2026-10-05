from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser
from app.services.call_outcome import classify

router = APIRouter()


class OutcomeRequest(BaseModel):
    transcript: str = Field(..., min_length=3, max_length=8000)


@router.post("/classify")
async def classify_call(body: OutcomeRequest, _: CurrentUser) -> dict:
    return {"kind": "call_outcome", **classify(body.transcript)}
