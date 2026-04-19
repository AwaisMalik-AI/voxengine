"""VoxEngine FastAPI application entrypoint."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import auth, campaigns, dnc, tts, usage, voices
from app.core.config import settings
from app.core.database import init_db

Path(settings.STORAGE_PATH).mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    (Path(settings.STORAGE_PATH) / "tts").mkdir(exist_ok=True)
    (Path(settings.STORAGE_PATH) / "campaigns").mkdir(exist_ok=True)
    (Path(settings.STORAGE_PATH) / "previews").mkdir(exist_ok=True)
    await init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="AI voice pipeline and TTS campaign platform for healthcare appointment reminders.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/storage", StaticFiles(directory=settings.STORAGE_PATH), name="storage")

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(voices.router, prefix="/api/voices", tags=["voices"])
app.include_router(tts.router, prefix="/api/tts", tags=["tts"])
app.include_router(campaigns.router, prefix="/api/campaigns", tags=["campaigns"])
app.include_router(dnc.router, prefix="/api/dnc", tags=["dnc"])
app.include_router(usage.router, prefix="/api/usage", tags=["usage"])


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok", "service": settings.APP_NAME}


@app.get("/", tags=["root"])
async def root() -> dict:
    return {"name": settings.APP_NAME, "docs": "/docs", "health": "/health"}
