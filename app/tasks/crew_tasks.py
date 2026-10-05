from app.services.voice_crew import VoiceCrew
from app.tasks.celery_app import celery_app


@celery_app.task(name="voxengine.run_voice_crew")
def run_voice_crew_task(purpose: str, patient_name: str = "there", when: str = "tomorrow") -> dict:
    result = VoiceCrew().run(purpose, patient_name, when)
    return {
        "crew": result.crew,
        "used_llm": result.used_llm,
        "intent": result.intent,
        "script": result.script,
        "steps": result.steps,
    }
