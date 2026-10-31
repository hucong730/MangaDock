from mangadock_worker.celery_app import celery_app
from mangadock_worker import (
    character_tasks,
    dubbing_tasks,
    pipeline_tasks,
    render_tasks,
    storyboard_tasks,
)


@celery_app.task
def ping() -> str:
    return "pong"
