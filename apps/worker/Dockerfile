FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY packages/core/src packages/core/src
COPY packages/providers/pyproject.toml packages/providers/pyproject.toml
COPY packages/providers/src packages/providers/src
COPY packages/persistence/pyproject.toml packages/persistence/pyproject.toml
COPY packages/persistence/src packages/persistence/src
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY apps/worker/src apps/worker/src
RUN pip install --no-cache-dir \
    ./packages/providers \
    ./packages/persistence \
    ./packages/core \
    ./apps/worker

CMD ["celery", "-A", "mangadock_worker.celery_app:celery_app", "worker", "--loglevel=INFO", "--concurrency=2"]
