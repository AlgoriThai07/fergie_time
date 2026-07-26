import os

from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

app = Celery(
    "fergie_time", broker=REDIS_URL, backend=REDIS_URL, include=["tasks.ingestion"]
)

# Celery Configuration
app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    result_expires=86400,  # 24 hours
)

# Celery Beat Schedule
app.conf.beat_schedule = {
    "run-fpl-ingestion-daily": {
        "task": "tasks.ingestion.run_fpl_ingestion",
        "schedule": crontab(hour="3", minute="0"),  # Daily at 3:00 AM UTC
    },
}
