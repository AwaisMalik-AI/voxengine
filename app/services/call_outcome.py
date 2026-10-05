"""Classify a call transcript into outcome + sentiment."""

from __future__ import annotations

POS = ("confirm", "yes", "see you", "thanks", "great")
NEG = ("cancel", "stop", "wrong number", "angry", "complaint")
RESCHEDULE = ("reschedule", "another day", "later", "next week")


def classify(transcript: str) -> dict:
    text = (transcript or "").lower()
    if any(w in text for w in RESCHEDULE):
        outcome = "rescheduled"
    elif any(w in text for w in NEG):
        outcome = "negative"
    elif any(w in text for w in POS):
        outcome = "confirmed"
    else:
        outcome = "no_decision"
    sentiment = "negative" if outcome == "negative" else "positive" if outcome == "confirmed" else "neutral"
    return {
        "outcome": outcome,
        "sentiment": sentiment,
        "follow_up": outcome in {"negative", "no_decision", "rescheduled"},
    }
