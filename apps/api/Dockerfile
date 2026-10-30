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
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/api/src apps/api/src
RUN pip install --no-cache-dir \
    ./packages/providers \
    ./packages/persistence \
    ./packages/core \
    ./apps/api

EXPOSE 8000

CMD ["uvicorn", "mangadock_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
