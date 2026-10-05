import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/vox")
os.environ.setdefault("SECRET_KEY", "x" * 40)

from app.services.voice_crew import VoiceCrew


def test_voice_crew_fallback():
    result = VoiceCrew().run("Remind the patient about a dental cleaning", "Alex", "Friday at 10am")
    assert result.crew == "voice"
    assert result.script
    assert len(result.steps) == 3
