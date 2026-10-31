import copy
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from mangadock_persistence.models import (
    CharacterRecord,
    ProjectAssetRecord,
    ProjectRecord,
    ProjectStageRecord,
)
from mangadock_providers import MockTTSProvider
from mangadock_worker import dubbing_tasks
from mangadock_worker.dubbing_tasks import run_dubbing_stage
from mangadock_worker.storyboard_tasks import run_storyboard_stage
from test_character_tasks import project_factory
from test_storyboard_tasks import complete_characters


@pytest.fixture
def tts_provider():
    return MockTTSProvider(output_dir="unused")


@pytest.fixture(autouse=True)
def isolate_dubbing(monkeypatch: pytest.MonkeyPatch, tts_provider):
    def factory(project_id, episode, output_dir):
        tts_provider._output_dir = Path(output_dir)
        return tts_provider

    monkeypatch.setattr(dubbing_tasks, "tts_for_project", factory)
    monkeypatch.setattr(dubbing_tasks, "enqueue_render", Mock())


async def prepare_project(project_factory):
    create_project, session_factory = project_factory
    project_id = await create_project()
    await complete_characters(project_id, session_factory)
    assert await run_storyboard_stage(project_id)
    return project_id, session_factory


async def asset(session_factory, project_id):
    async with session_factory() as session:
        return await session.scalar(
            select(ProjectAssetRecord).where(
                ProjectAssetRecord.project_id == project_id,
                ProjectAssetRecord.kind == "dubbing",
            )
        )


async def stage(session_factory, project_id, name):
    async with session_factory() as session:
        return await session.scalar(
            select(ProjectStageRecord).where(
                ProjectStageRecord.project_id == project_id,
                ProjectStageRecord.stage == name,
            )
        )


@pytest.mark.asyncio
async def test_dubbing_generates_timed_audio_and_reuses_valid_asset(
    project_factory,
    tts_provider,
) -> None:
    project_id, session_factory = await prepare_project(project_factory)

    assert await run_dubbing_stage(project_id, 1) is True
    first = await asset(session_factory, project_id)
    lines = first.payload_json["episodes"][0]["lines"]
    assert [line["line_id"] for line in lines] == ["1:1:2", "1:1:4"]
    assert lines[0]["start_s"] == 0
    assert lines[0]["end_s"] == lines[0]["duration_s"]
    assert lines[1]["start_s"] == 3
    assert lines[1]["end_s"] == 3 + lines[1]["duration_s"]
    assert all(not line["audio_path"].startswith("/") for line in lines)
    assert len(tts_provider.calls) == 2
    dubbing_tasks.enqueue_render.assert_called_once_with(project_id, 1)

    assert await run_dubbing_stage(project_id, 1) is True
    assert len(tts_provider.calls) == 2


@pytest.mark.asyncio
async def test_second_episode_dubbing_uses_valid_full_script(
    project_factory,
    tts_provider,
) -> None:
    project_id, session_factory = await prepare_project(project_factory)

    assert await run_dubbing_stage(project_id, 2) is True

    lines = (await asset(session_factory, project_id)).payload_json["episodes"][0]["lines"]
    assert [line["line_id"] for line in lines] == ["2:1:2", "2:1:4"]
    assert len(tts_provider.calls) == 2


@pytest.mark.asyncio
async def test_voice_profile_change_invalidates_dubbing(
    project_factory,
    tts_provider,
) -> None:
    project_id, session_factory = await prepare_project(project_factory)
    assert await run_dubbing_stage(project_id, 1)
    async with session_factory() as session:
        character = await session.scalar(
            select(CharacterRecord).where(CharacterRecord.project_id == project_id).limit(1)
        )
        character.voice_prompt = "全新的少年音色"
        await session.commit()

    assert await run_dubbing_stage(project_id, 1) is True

    assert len(tts_provider.calls) == 3


@pytest.mark.asyncio
async def test_overlong_line_is_failed_and_does_not_start_render(
    project_factory,
) -> None:
    project_id, session_factory = await prepare_project(project_factory)
    async with session_factory() as session:
        project = await session.get(ProjectRecord, project_id)
        payload = copy.deepcopy(project.script_json)
        payload["episodes"][0]["scenes"][0]["lines"][0]["text"] = "这是一句长度远远超过当前镜头三秒时长限制的台词"
        project.script_json = payload
        await session.commit()

    assert await run_dubbing_stage(project_id, 1) is False

    failed = (await asset(session_factory, project_id)).payload_json["episodes"][0]["lines"][0]
    assert failed["status"] == "failed"
    assert failed["duration_s"] > 3
    assert failed["end_s"] > 3
    dubbing_tasks.enqueue_render.assert_not_called()
    assert (await stage(session_factory, project_id, "dubbing")).status == "failed"


@pytest.mark.asyncio
async def test_render_enqueue_failure_is_retryable(project_factory) -> None:
    project_id, session_factory = await prepare_project(project_factory)
    dubbing_tasks.enqueue_render.side_effect = RuntimeError("broker down")

    assert await run_dubbing_stage(project_id, 1) is False

    assert (await stage(session_factory, project_id, "dubbing")).status == "done"
    render = await stage(session_factory, project_id, "render")
    assert render.status == "failed"
    assert render.requires_attention is True
    assert "入队失败" in render.error
