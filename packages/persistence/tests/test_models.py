import os

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from mangadock_persistence.database import Base
from mangadock_persistence.models import (
    LLMProviderRecord,
    ProjectEpisodeRecord,
    ProjectRecord,
    ProjectStageRecord,
)


@pytest.mark.asyncio
async def test_project_models_persist_json_and_stage_defaults() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as connection:
        provider = LLMProviderRecord(
            name="fake",
            base_url="https://api.example.com/v1",
            model="fake-model",
            api_key_env="OPENAI_API_KEY",
            enabled=True,
        )
        connection.add(provider)
        await connection.flush()
        project = ProjectRecord(
            title="旧港",
            source_filename="harbor.txt",
            source_media_type="text/plain",
            provider_id=provider.id,
            novel_json={
                "title": "旧港",
                "chapters": [{"index": 1, "title": "正文", "text": "内容"}],
            },
        )
        connection.add(project)
        await connection.flush()
        connection.add_all(
            [
                ProjectStageRecord(project_id=project.id, stage="outline"),
                ProjectStageRecord(
                    project_id=project.id,
                    stage="script",
                    total_items=2,
                ),
                ProjectEpisodeRecord(project_id=project.id, episode=1),
            ]
        )
        await connection.commit()
        await connection.refresh(project)

        assert project.id is not None
        assert project.novel_json["title"] == "旧港"
        assert project.outline_json is None
        assert project.script_json is None
        assert project.created_at is not None
        result = await connection.scalars(
            select(ProjectStageRecord).where(
                ProjectStageRecord.project_id == project.id
            )
        )
        stages = list(result.all())
        assert [stage.status for stage in stages] == ["pending", "pending"]
        assert stages[0].requires_attention is False
        assert stages[1].total_items == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_episode_number_is_unique_per_project() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as connection:
        provider = LLMProviderRecord(
            name="fake",
            base_url="https://api.example.com/v1",
            model="fake-model",
            api_key_env="OPENAI_API_KEY",
        )
        connection.add(provider)
        await connection.flush()
        project = ProjectRecord(
            title="旧港",
            source_filename="harbor.txt",
            source_media_type="text/plain",
            provider_id=provider.id,
            novel_json={"title": "旧港", "chapters": []},
        )
        connection.add(project)
        await connection.flush()
        connection.add(ProjectEpisodeRecord(project_id=project.id, episode=1))
        connection.add(ProjectEpisodeRecord(project_id=project.id, episode=1))
        with pytest.raises(IntegrityError):
            await connection.commit()
    await engine.dispose()
