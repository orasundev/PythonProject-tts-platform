from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "tts_platform",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.tts_tasks",
        "app.tasks.webhook_tasks",
        "app.tasks.maintenance_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "app.tasks.tts_tasks.generate_tts_job": {"queue": "tts"},
        "app.tasks.tts_tasks.generate_tts_job_priority": {"queue": "tts_priority"},
        "app.tasks.webhook_tasks.deliver_webhook": {"queue": "webhooks"},
        "app.tasks.maintenance_tasks.*": {"queue": "maintenance"},
    },
    beat_schedule={
        "expire-old-files-nightly": {
            "task": "app.tasks.maintenance_tasks.expire_old_files",
            "schedule": 86400,  # every 24 hours
        },
        "reset-monthly-quotas": {
            "task": "app.tasks.maintenance_tasks.reset_expired_quotas",
            "schedule": 3600,  # check every hour
        },
    },
)
