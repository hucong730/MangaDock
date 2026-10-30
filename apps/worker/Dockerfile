FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY apps/worker/src apps/worker/src
RUN pip install --no-cache-dir ./apps/worker

CMD ["celery", "-A", "mangadock_worker.celery_app:celery_app", "worker", "--loglevel=INFO", "--concurrency=2"]
