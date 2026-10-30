import os

os.environ["REDIS_URL"] = "redis://localhost:6379/9"

from mangadock_worker.celery_app import celery_app
from mangadock_worker.tasks import ping


def test_ping_returns_pong() -> None:
    assert ping.run() == "pong"
    assert ping.name == "mangadock_worker.tasks.ping"


def test_celery_uses_redis_for_broker_and_results() -> None:
    assert celery_app.conf.broker_url == "redis://localhost:6379/9"
    assert celery_app.conf.result_backend == "redis://localhost:6379/9"
