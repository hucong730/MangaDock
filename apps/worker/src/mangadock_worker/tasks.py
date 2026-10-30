from mangadock_worker.celery_app import celery_app
from mangadock_worker import pipeline_tasks


@celery_app.task
def ping() -> str:
    return "pong"
