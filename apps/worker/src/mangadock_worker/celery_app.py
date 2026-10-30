import os

from celery import Celery

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "mangadock",
    broker=redis_url,
    backend=redis_url,
    include=["mangadock_worker.tasks"],
)
