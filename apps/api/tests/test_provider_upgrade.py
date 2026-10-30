import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from mangadock_api.main import ensure_provider_capabilities
from mangadock_api.models import LLMProviderRecord, ProviderCapabilityRecord
from mangadock_persistence.database import Base


@pytest.mark.asyncio
async def test_existing_providers_receive_default_script_capability() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(
            LLMProviderRecord(
                name="legacy",
                base_url="https://api.example.com/v1",
                model="legacy-model",
                api_key_env="OPENAI_API_KEY",
            )
        )
        await session.commit()
    async with engine.begin() as connection:
        await ensure_provider_capabilities(connection)
        await ensure_provider_capabilities(connection)

        capabilities = list(
            (
                await connection.scalars(
                    select(ProviderCapabilityRecord.capability)
                )
            ).all()
        )
        assert capabilities == ["script"]
    await engine.dispose()
