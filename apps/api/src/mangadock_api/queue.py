from celery import Celery

from mangadock_api.config import settings

celery_app = Celery("mangadock-api", broker=settings.redis_url)


def enqueue_task(task_name: str, *args: object) -> None:
    celery_app.send_task(task_name, args=args)
