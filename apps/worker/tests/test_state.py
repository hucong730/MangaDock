import os

import pytest
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
from mangadock_worker.state import (
    increment_stage_progress,
    update_episode,
    update_stage,
)


@pytest.mark.asyncio
async def test_stage_and_episode_state_updates() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        provider = LLMProviderRecord(
            name="fake",
            base_url="https://api.example.com/v1",
            model="fake",
            api_key_env="OPENAI_API_KEY",
        )
        session.add(provider)
        await session.flush()
        project = ProjectRecord(
            title="旧港",
            source_filename="novel.txt",
            source_media_type="text/plain",
            provider_id=provider.id,
            novel_json={"title": "旧港", "chapters": []},
        )
        session.add(project)
        await session.flush()
        session.add_all(
            [
                ProjectStageRecord(project_id=project.id, stage="script"),
                ProjectEpisodeRecord(project_id=project.id, episode=1),
            ]
        )
        await session.commit()
        project_id = project.id

    async with session_factory() as session:
        running = await update_stage(
            session,
            project_id,
            "script",
            status="running",
            total_items=2,
            attempt_count=1,
        )
        assert running.status == "running"
        assert running.total_items == 2
        assert running.attempt_count == 1

        await increment_stage_progress(session, project_id, "script")
        await increment_stage_progress(session, project_id, "script")
        done = await update_stage(
            session,
            project_id,
            "script",
            status="done",
        )
        assert done.completed_items == 2

        episode = await update_episode(
            session,
            project_id,
            1,
            status="done",
            attempt_count=1,
            payload_json={"episode": 1},
        )
        assert episode.status == "done"
        assert episode.payload_json == {"episode": 1}

        failed = await update_stage(
            session,
            project_id,
            "script",
            status="failed",
            error="Invalid output",
            requires_attention=True,
        )
        assert failed.status == "failed"
        assert failed.error == "Invalid output"
        assert failed.requires_attention is True
    await engine.dispose()
