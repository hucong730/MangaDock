import asyncio
import copy
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from mangadock_persistence.models import (
    ProjectAssetRecord,
    ProjectStageRecord,
    ProjectVideoRouteRecord,
    VideoProviderRecord,
)
from mangadock_providers import MockVideoProvider, VideoProviderAPIError
from mangadock_worker import dubbing_tasks, render_tasks, video_factory
from mangadock_worker.asset_store import upsert_project_asset
from mangadock_worker.dubbing_tasks import run_dubbing_stage
from mangadock_worker.pipeline_tasks import new_session
from mangadock_worker.render_tasks import (
    run_finish_render,
    run_render_segment,
    retry_render_cut,
)
from test_character_tasks import project_factory
from test_dubbing_tasks import prepare_project


class TrackingVideoProvider(MockVideoProvider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.active = 0
        self.max_active = 0

    async def generate(self, keyframe_image, prompt, duration_s, config):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.02)
        try:
            return await super().generate(keyframe_image, prompt, duration_s, config)
        finally:
            self.active -= 1


@pytest.fixture
def video_provider():
    return TrackingVideoProvider(output_dir="unused")


@pytest.fixture(autouse=True)
def isolate_render(monkeypatch: pytest.MonkeyPatch, video_provider, tmp_path):
    def tts_factory(project_id, episode, output_dir):
        from mangadock_providers import MockTTSProvider
        return MockTTSProvider(output_dir=output_dir)

    monkeypatch.setattr(dubbing_tasks, "tts_for_project", tts_factory)
    monkeypatch.setattr(dubbing_tasks, "enqueue_render", Mock())
    monkeypatch.setattr(render_tasks, "enqueue_compose", Mock())

    def factory(record, output_dir):
        video_provider._output_dir = Path(output_dir)
        return video_provider

    monkeypatch.setattr(render_tasks, "video_for_record", factory)


async def prepare_render(project_factory):
    project_id, session_factory = await prepare_project(project_factory)
    assert await run_dubbing_stage(project_id, 1)
    return project_id, session_factory


async def render_asset(session_factory, project_id):
    async with session_factory() as session:
        return await session.scalar(
            select(ProjectAssetRecord).where(
                ProjectAssetRecord.project_id == project_id,
                ProjectAssetRecord.kind == "render",
            )
        )


@pytest.mark.asyncio
async def test_render_generates_and_reuses_clips(project_factory, video_provider) -> None:
    project_id, session_factory = await prepare_render(project_factory)

    assert await run_render_segment(project_id, 1, 1) is True
    assert await run_finish_render(project_id, 1) is True

    cuts = (await render_asset(session_factory, project_id)).payload_json["episodes"][0]["segments"][0]["cuts"]
    assert [cut["status"] for cut in cuts] == ["done", "done"]
    assert all(cut["clip_path"].startswith(f"projects/{project_id}/clips/episode_1/") for cut in cuts)
    assert len(video_provider.calls) == 2
    render_tasks.enqueue_compose.assert_called_once_with(project_id, 1)

    assert await run_render_segment(project_id, 1, 1) is True
    assert len(video_provider.calls) == 2


@pytest.mark.asyncio
async def test_failed_cut_retries_twice_then_single_cut_retry(project_factory, video_provider) -> None:
    project_id, session_factory = await prepare_render(project_factory)
    original_generate = video_provider.generate

    async def fail_first_cut(keyframe_image, prompt, duration_s, config):
        if "双人中景" in prompt:
            raise VideoProviderAPIError("first cut failed")
        return await original_generate(keyframe_image, prompt, duration_s, config)

    video_provider.generate = fail_first_cut

    assert await run_render_segment(project_id, 1, 1) is False
    assert await run_finish_render(project_id, 1) is False
    render_tasks.enqueue_compose.assert_not_called()
    cuts = (await render_asset(session_factory, project_id)).payload_json["episodes"][0]["segments"][0]["cuts"]
    assert cuts[0]["status"] == "failed"
    assert cuts[0]["attempt_count"] == 2
    assert cuts[1]["status"] == "done"
    successful_path = cuts[1]["clip_path"]
    calls_before_retry = len(video_provider.calls)

    video_provider.generate = original_generate
    assert await retry_render_cut(project_id, 1, 1, 1) is True

    retried = (await render_asset(session_factory, project_id)).payload_json["episodes"][0]["segments"][0]["cuts"]
    assert retried[0]["status"] == "done"
    assert retried[1]["clip_path"] == successful_path
    assert len(video_provider.calls) == calls_before_retry + 1
    render_tasks.enqueue_compose.assert_called_once_with(project_id, 1)


@pytest.mark.asyncio
async def test_segment_route_and_provider_concurrency(project_factory, video_provider) -> None:
    project_id, session_factory = await prepare_render(project_factory)
    async with session_factory() as session:
        provider = VideoProviderRecord(
            name="seedance-dialogue",
            kind="seedance",
            base_url="https://ark.test/api/v3",
            model="seedance-test",
            api_key_env="ARK_API_KEY",
            config_json={"max_concurrency": 1},
        )
        session.add(provider)
        await session.flush()
        session.add(
            ProjectVideoRouteRecord(
                project_id=project_id,
                episode=1,
                segment_index=1,
                video_provider_id=provider.id,
            )
        )
        await session.commit()

    assert await run_render_segment(project_id, 1, 1) is True

    cuts = (await render_asset(session_factory, project_id)).payload_json["episodes"][0]["segments"][0]["cuts"]
    assert all(cut["provider_id"] == provider.id for cut in cuts)
    assert video_provider.max_active == 1


@pytest.mark.asyncio
async def test_live_mode_requires_video_route(project_factory, monkeypatch) -> None:
    project_id, session_factory = await prepare_render(project_factory)
    monkeypatch.setenv("MANGADOCK_VIDEO_MODE", "live")
    monkeypatch.setattr(render_tasks, "video_for_record", video_factory.video_for_record)

    assert await run_render_segment(project_id, 1, 1) is False

    cuts = (await render_asset(session_factory, project_id)).payload_json["episodes"][0]["segments"][0]["cuts"]
    assert all(cut["status"] == "failed" for cut in cuts)
    assert "route" in cuts[0]["error"]


@pytest.mark.asyncio
async def test_changed_keyframe_is_not_committed(project_factory, video_provider) -> None:
    project_id, session_factory = await prepare_render(project_factory)
    original_generate = video_provider.generate

    async def stale_generate(keyframe_image, prompt, duration_s, config):
        async with new_session() as session:
            asset = await session.scalar(
                select(ProjectAssetRecord).where(
                    ProjectAssetRecord.project_id == project_id,
                    ProjectAssetRecord.kind == "storyboard",
                )
            )
            payload = copy.deepcopy(asset.payload_json)
            payload["episodes"][0]["segments"][0]["cuts"][0]["keyframe_image"]["path"] = "projects/1/images/changed.png"
            await upsert_project_asset(session, project_id, "storyboard", payload)
        return await original_generate(keyframe_image, prompt, duration_s, config)

    video_provider.generate = stale_generate

    assert await run_render_segment(project_id, 1, 1) is False

    first = (await render_asset(session_factory, project_id)).payload_json["episodes"][0]["segments"][0]["cuts"][0]
    assert first["status"] == "outdated"
    assert first["clip_path"] is None


@pytest.mark.asyncio
async def test_parallel_segments_preserve_all_completed_clips(project_factory, video_provider) -> None:
    project_id, session_factory = await prepare_render(project_factory)
    async with session_factory() as session:
        storyboard = await session.scalar(
            select(ProjectAssetRecord).where(
                ProjectAssetRecord.project_id == project_id,
                ProjectAssetRecord.kind == "storyboard",
            )
        )
        payload = copy.deepcopy(storyboard.payload_json)
        second_segment = copy.deepcopy(payload["episodes"][0]["segments"][0])
        second_segment["index"] = 2
        payload["episodes"][0]["segments"].append(second_segment)
        await upsert_project_asset(session, project_id, "storyboard", payload)
    await render_tasks.ensure_render_episode(project_id, 1)

    results = await asyncio.gather(
        run_render_segment(project_id, 1, 1),
        run_render_segment(project_id, 1, 2),
    )

    assert all(results)
    segments = (await render_asset(session_factory, project_id)).payload_json["episodes"][0]["segments"]
    assert [cut["status"] for segment in segments for cut in segment["cuts"]] == ["done"] * 4
    assert len(video_provider.calls) == 4


@pytest.mark.asyncio
async def test_single_cut_retry_leaves_other_failed_cut_untouched(project_factory, video_provider) -> None:
    project_id, session_factory = await prepare_render(project_factory)
    original_generate = video_provider.generate

    async def fail_both(keyframe_image, prompt, duration_s, config):
        raise VideoProviderAPIError("both failed")

    video_provider.generate = fail_both
    assert await run_render_segment(project_id, 1, 1) is False
    calls_before = len(video_provider.calls)

    video_provider.generate = original_generate
    assert await retry_render_cut(project_id, 1, 1, 1) is False

    cuts = (await render_asset(session_factory, project_id)).payload_json["episodes"][0]["segments"][0]["cuts"]
    assert cuts[0]["status"] == "done"
    assert cuts[1]["status"] == "failed"
    assert len(video_provider.calls) == calls_before + 1


@pytest.mark.asyncio
async def test_start_render_creates_segment_chord(
    project_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id, _ = await prepare_render(project_factory)
    chord = Mock()
    monkeypatch.setattr(render_tasks, "chord", chord)

    await asyncio.to_thread(render_tasks.start_render.run, project_id, 1)

    group = chord.call_args.args[0]
    assert len(group.tasks) == 1
    chord.return_value.delay.assert_called_once_with()
