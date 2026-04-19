"""TTS abstraction: Edge-TTS (free) and OpenAI TTS."""

from __future__ import annotations

import asyncio
import io
import time
from typing import Any, Literal

import httpx

from app.core.config import settings
from app.models.voice import VoiceProfile


class TTSEngine:
    """Generate speech audio from text using configured backends."""

    def __init__(self) -> None:
        self._openai_base = "https://api.openai.com/v1/audio/speech"

    async def generate(self, text: str, voice: VoiceProfile) -> bytes:
        engine = voice.tts_engine or settings.TTS_ENGINE
        if engine == "openai":
            return await self._generate_openai_tts(text, voice)
        return await self._generate_edge_tts(text, voice)

    async def _generate_edge_tts(self, text: str, voice: VoiceProfile) -> bytes:
        import edge_tts

        communicate = edge_tts.Communicate(text, voice.voice_id_external)
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        return buf.getvalue()

    async def _generate_openai_tts(self, text: str, voice: VoiceProfile) -> bytes:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "model": settings.OPENAI_TTS_MODEL,
            "input": text,
            "voice": voice.voice_id_external or settings.OPENAI_TTS_VOICE,
            "response_format": "mp3",
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(self._openai_base, headers=headers, json=body)
            r.raise_for_status()
            return r.content

    async def list_available_voices(self, engine: Literal["edge_tts", "openai"] | None = None) -> list[dict[str, Any]]:
        eng = engine or settings.TTS_ENGINE
        if eng == "openai":
            return self._openai_voice_catalog()
        return await self._list_edge_voices()

    async def _list_edge_voices(self) -> list[dict[str, Any]]:
        import edge_tts

        voices = await edge_tts.list_voices()
        return [
            {
                "id": v["ShortName"],
                "name": v.get("FriendlyName"),
                "locale": v.get("Locale"),
                "gender": v.get("Gender"),
                "engine": "edge_tts",
            }
            for v in voices
        ]

    def _openai_voice_catalog(self) -> list[dict[str, Any]]:
        names = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
        return [
            {"id": n, "name": n.title(), "locale": None, "gender": None, "engine": "openai"}
            for n in names
        ]

    @staticmethod
    def estimate_duration(text: str, words_per_minute: float = 150.0) -> float:
        words = max(len(text.split()), 1)
        return round((words / words_per_minute) * 60.0, 2)

    async def generate_with_timing(self, text: str, voice: VoiceProfile) -> tuple[bytes, int]:
        start = time.perf_counter()
        audio = await self.generate(text, voice)
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return audio, elapsed_ms


def run_async(coro):
    """Run coroutine from sync context (e.g. Celery)."""
    return asyncio.run(coro)
