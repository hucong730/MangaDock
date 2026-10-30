FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/api/src apps/api/src
RUN pip install --no-cache-dir ./apps/api

EXPOSE 8000

CMD ["uvicorn", "mangadock_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
