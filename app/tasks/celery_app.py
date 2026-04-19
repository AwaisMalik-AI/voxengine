"""Celery application with queue routing for TTS, outbound calls, and webhooks."""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "voxengine",
    broker=settings.celery_broker,
    backend=settings.celery_backend,
    include=["app.tasks.tts_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,
    task_soft_time_limit=540,
    task_routes={
        "app.tasks.tts_tasks.generate_tts_task": {"queue": "tts"},
        "app.tasks.tts_tasks.campaign_call_task": {"queue": "calls"},
        "app.tasks.tts_tasks.deliver_webhook_task": {"queue": "webhooks"},
    },
    task_default_queue="default",
)
