from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import SQLAlchemyError

from mangadock_api.database import get_db
from mangadock_api.main import app


@pytest.mark.asyncio
async def test_health_returns_database_status(client: AsyncClient) -> None:
    response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


@pytest.mark.asyncio
async def test_health_returns_503_when_database_is_unavailable(
    client: AsyncClient,
) -> None:
    session = AsyncMock()
    session.execute.side_effect = SQLAlchemyError("private connection details")

    async def broken_db() -> AsyncIterator[AsyncMock]:
        yield session

    app.dependency_overrides[get_db] = broken_db

    response = await client.get("/healthz")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
    assert "private connection details" not in response.text
