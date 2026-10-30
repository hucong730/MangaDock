import asyncio
import os
from unittest.mock import Mock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["MANGADOCK_LLM_MODE"] = "fake"
os.environ["REDIS_URL"] = "redis://localhost:6379/9"

from mangadock_persistence.database import Base
from mangadock_persistence.models import (
    LLMProviderRecord,
    ProjectEpisodeRecord,
    ProjectRecord,
    ProjectStageRecord,
)
from mangadock_providers import FakeLLMProvider, ProviderResponseError
from mangadock_worker import pipeline_tasks
from mangadock_worker.pipeline_tasks import (
    run_stage_episode,
    run_stage_outline,
    run_stage_script,
    start_script,
)


class SequenceProvider(FakeLLMProvider):
    def __init__(self, failures: int) -> None:
        super().__init__()
        self.remaining_failures = failures

    async def chat(self, messages, schema):
        if self.remaining_failures:
            self.remaining_failures -= 1
            raise ProviderResponseError("Invalid structured output")
        return await super().chat(messages, schema)


@pytest_asyncio.fixture
async def project_factory(monkeypatch: pytest.MonkeyPatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(pipeline_tasks, "SessionLocal", session_factory)
    monkeypatch.setattr(start_script, "delay", Mock())
    monkeypatch.setattr("mangadock_worker.character_tasks.stage_characters.delay", Mock())

    async def create_project() -> int:
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
                novel_json={
                    "title": "旧港",
                    "chapters": [{"index": 1, "title": "正文", "text": "内容"}],
                },
            )
            session.add(project)
            await session.flush()
            session.add_all(
                [
                    ProjectStageRecord(
                        project_id=project.id,
                        stage="outline",
                        total_items=1,
                    ),
                    ProjectStageRecord(project_id=project.id, stage="script"),
                ]
            )
            await session.commit()
            return project.id

    original_provider = pipeline_tasks.provider_for_record
    yield create_project, session_factory
    pipeline_tasks.provider_for_record = original_provider
    await engine.dispose()


async def get_stage(session_factory, project_id: int, stage: str):
    async with session_factory() as session:
        return await session.scalar(
            select(ProjectStageRecord).where(
                ProjectStageRecord.project_id == project_id,
                ProjectStageRecord.stage == stage,
            )
        )


@pytest.mark.asyncio
async def test_outline_retries_once_then_starts_script(project_factory) -> None:
    create_project, session_factory = project_factory
    project_id = await create_project()
    provider = SequenceProvider(failures=1)
    pipeline_tasks.provider_for_record = lambda _: provider

    assert await run_stage_outline(project_id) is True

    assert len(provider.calls) == 1
    stage = await get_stage(session_factory, project_id, "outline")
    assert stage.status == "done"
    assert stage.attempt_count == 2
    async with session_factory() as session:
        project = await session.get(ProjectRecord, project_id)
        episodes = list(
            (
                await session.scalars(
                    select(ProjectEpisodeRecord).where(
                        ProjectEpisodeRecord.project_id == project_id
                    )
                )
            ).all()
        )
    assert project.outline_json is not None
    assert len(episodes) == 2
    start_script.delay.assert_called_once_with(project_id)


@pytest.mark.asyncio
async def test_outline_marks_manual_attention_after_two_failures(project_factory) -> None:
    create_project, session_factory = project_factory
    project_id = await create_project()
    provider = SequenceProvider(failures=2)
    pipeline_tasks.provider_for_record = lambda _: provider

    assert await run_stage_outline(project_id) is False

    stage = await get_stage(session_factory, project_id, "outline")
    assert stage.status == "failed"
    assert stage.requires_attention is True
    assert stage.attempt_count == 2
    assert "Invalid structured output" in stage.error
    start_script.delay.assert_not_called()


@pytest.mark.asyncio
async def test_episodes_and_script_are_sorted_and_completed(project_factory) -> None:
    create_project, session_factory = project_factory
    project_id = await create_project()
    pipeline_tasks.provider_for_record = lambda _: FakeLLMProvider()
    assert await run_stage_outline(project_id)

    assert await run_stage_episode(project_id, 2) is True
    assert await run_stage_episode(project_id, 1) is True
    assert await run_stage_script(project_id) is True

    stage = await get_stage(session_factory, project_id, "script")
    assert stage.status == "done"
    assert stage.completed_items == 2
    async with session_factory() as session:
        project = await session.get(ProjectRecord, project_id)
    assert [episode["episode"] for episode in project.script_json["episodes"]] == [1, 2]


@pytest.mark.asyncio
async def test_failed_episode_fails_script_after_other_episode_finishes(
    project_factory,
) -> None:
    create_project, session_factory = project_factory
    project_id = await create_project()
    pipeline_tasks.provider_for_record = lambda _: FakeLLMProvider()
    assert await run_stage_outline(project_id)
    pipeline_tasks.provider_for_record = lambda _: SequenceProvider(failures=99)

    assert await run_stage_episode(project_id, 1) is False
    pipeline_tasks.provider_for_record = lambda _: FakeLLMProvider()
    assert await run_stage_episode(project_id, 2) is True
    assert await run_stage_script(project_id) is False

    stage = await get_stage(session_factory, project_id, "script")
    assert stage.status == "failed"
    assert stage.completed_items == 2
    async with session_factory() as session:
        project = await session.get(ProjectRecord, project_id)
        failed_episode = await session.scalar(
            select(ProjectEpisodeRecord).where(
                ProjectEpisodeRecord.project_id == project_id,
                ProjectEpisodeRecord.episode == 1,
            )
        )
    assert project.script_json is None
    assert failed_episode.status == "failed"


@pytest.mark.asyncio
async def test_start_script_creates_chord_for_all_episodes(
    project_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_project, _ = project_factory
    project_id = await create_project()
    pipeline_tasks.provider_for_record = lambda _: FakeLLMProvider()
    assert await run_stage_outline(project_id)
    chord = Mock()
    monkeypatch.setattr(pipeline_tasks, "chord", chord)

    await asyncio.to_thread(start_script.run, project_id)

    group = chord.call_args.args[0]
    assert len(group.tasks) == 2
    chord.return_value.delay.assert_called_once_with()


@pytest.mark.asyncio
async def test_outline_to_script_enqueue_failure_is_retryable(project_factory) -> None:
    create_project, session_factory = project_factory
    project_id = await create_project()
    pipeline_tasks.provider_for_record = lambda _: FakeLLMProvider()
    start_script.delay.side_effect = RuntimeError("broker down")

    assert await run_stage_outline(project_id) is False

    outline = await get_stage(session_factory, project_id, "outline")
    script = await get_stage(session_factory, project_id, "script")
    assert outline.status == "done"
    assert script.status == "failed"
    assert script.requires_attention is True
    assert "入队失败" in script.error
    async with session_factory() as session:
        episodes = list(
            (
                await session.scalars(
                    select(ProjectEpisodeRecord).where(
                        ProjectEpisodeRecord.project_id == project_id
                    )
                )
            ).all()
        )
    assert len(episodes) == 2


@pytest.mark.asyncio
async def test_chord_enqueue_failure_marks_script_failed(
    project_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_project, session_factory = project_factory
    project_id = await create_project()
    pipeline_tasks.provider_for_record = lambda _: FakeLLMProvider()
    assert await run_stage_outline(project_id)
    chord = Mock()
    chord.return_value.delay.side_effect = RuntimeError("broker down")
    monkeypatch.setattr(pipeline_tasks, "chord", chord)

    await asyncio.to_thread(start_script.run, project_id)

    script = await get_stage(session_factory, project_id, "script")
    assert script.status == "failed"
    assert script.requires_attention is True
    assert "入队失败" in script.error


@pytest.mark.asyncio
async def test_script_to_characters_enqueue_failure_is_retryable(project_factory) -> None:
    create_project, session_factory = project_factory
    project_id = await create_project()
    pipeline_tasks.provider_for_record = lambda _: FakeLLMProvider()
    assert await run_stage_outline(project_id)
    assert await run_stage_episode(project_id, 1)
    assert await run_stage_episode(project_id, 2)
    from mangadock_worker.character_tasks import stage_characters

    stage_characters.delay.side_effect = RuntimeError("broker down")

    assert await run_stage_script(project_id) is False

    script = await get_stage(session_factory, project_id, "script")
    characters = await get_stage(session_factory, project_id, "characters")
    assert script.status == "done"
    assert characters.status == "failed"
    assert characters.requires_attention is True
    assert "入队失败" in characters.error
