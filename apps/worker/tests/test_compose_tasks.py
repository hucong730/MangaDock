import asyncio
import copy
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from mangadock_persistence.models import ProjectAssetRecord, ProjectStageRecord
from mangadock_core.pipeline.subtitles import subtitle_time
from mangadock_worker import dubbing_tasks
from mangadock_worker.asset_paths import asset_root
from mangadock_worker.compose_tasks import run_compose_stage
from mangadock_worker.media_processing import probe_video
from mangadock_worker.render_tasks import run_render_segment
from test_character_tasks import project_factory
from test_render_tasks import prepare_render, render_asset


@pytest.fixture(autouse=True)
def prevent_broker_enqueue(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(dubbing_tasks, "enqueue_render", Mock())


async def prepare_compose(project_factory):
    project_id, session_factory = await prepare_render(project_factory)
    assert await run_render_segment(project_id, 1, 1)
    return project_id, session_factory


async def compose_asset(session_factory, project_id):
    async with session_factory() as session:
        return await session.scalar(
            select(ProjectAssetRecord).where(
                ProjectAssetRecord.project_id == project_id,
                ProjectAssetRecord.kind == "compose",
            )
        )


async def compose_stage(session_factory, project_id):
    async with session_factory() as session:
        return await session.scalar(
            select(ProjectStageRecord).where(
                ProjectStageRecord.project_id == project_id,
                ProjectStageRecord.stage == "compose",
            )
        )


@pytest.mark.asyncio
async def test_compose_exports_four_artifacts_and_reuses_valid_export(project_factory) -> None:
    project_id, session_factory = await prepare_compose(project_factory)

    result = await run_compose_stage(project_id, 1)
    assert result is True, (await compose_stage(session_factory, project_id)).error

    export = (await compose_asset(session_factory, project_id)).payload_json["episodes"][0]
    for field in ("burned_path", "clean_path", "srt_path", "vtt_path"):
        assert (asset_root() / export[field]).is_file()
        assert not export[field].startswith("/")
    for field in ("burned_path", "clean_path"):
        metadata = await probe_video(asset_root() / export[field])
        video = next(stream for stream in metadata["streams"] if stream["codec_type"] == "video")
        assert video["codec_name"] == "h264"
        assert video["width"] == 1920
        assert video["height"] == 1080
        assert video["pix_fmt"] == "yuv420p"
        assert video["r_frame_rate"] == "24/1"
        assert float(metadata["format"]["duration"]) == pytest.approx(7, abs=0.2)
    srt = (asset_root() / export["srt_path"]).read_text(encoding="utf-8")
    async with session_factory() as session:
        dubbing = await session.scalar(
            select(ProjectAssetRecord).where(
                ProjectAssetRecord.project_id == project_id,
                ProjectAssetRecord.kind == "dubbing",
            )
        )
    for line in dubbing.payload_json["episodes"][0]["lines"]:
        expected = (
            f"{subtitle_time(line['start_s'], ',')} --> "
            f"{subtitle_time(line['end_s'], ',')}"
        )
        assert expected in srt
    clean_mtime = (asset_root() / export["clean_path"]).stat().st_mtime_ns

    assert await run_compose_stage(project_id, 1) is True
    assert (asset_root() / export["clean_path"]).stat().st_mtime_ns == clean_mtime


@pytest.mark.asyncio
async def test_subtitle_config_change_rebuilds_compose_only(project_factory, monkeypatch) -> None:
    project_id, session_factory = await prepare_compose(project_factory)
    assert await run_compose_stage(project_id, 1)
    before = (await compose_asset(session_factory, project_id)).payload_json["episodes"][0]
    before_mtime = (asset_root() / before["clean_path"]).stat().st_mtime_ns
    render_before = (await render_asset(session_factory, project_id)).payload_json
    monkeypatch.setenv("SUBTITLE_FONT_SIZE", "36")
    await asyncio.sleep(1.1)

    assert await run_compose_stage(project_id, 1) is True

    after = (await compose_asset(session_factory, project_id)).payload_json["episodes"][0]
    assert after["source_fingerprint"] != before["source_fingerprint"]
    assert (asset_root() / after["clean_path"]).stat().st_mtime_ns > before_mtime
    assert (await render_asset(session_factory, project_id)).payload_json == render_before


@pytest.mark.asyncio
async def test_zero_dialogue_exports_silent_episode(project_factory) -> None:
    project_id, session_factory = await prepare_compose(project_factory)
    async with session_factory() as session:
        asset = await session.scalar(
            select(ProjectAssetRecord).where(
                ProjectAssetRecord.project_id == project_id,
                ProjectAssetRecord.kind == "dubbing",
            )
        )
        payload = copy.deepcopy(asset.payload_json)
        payload["episodes"][0]["lines"] = []
        asset.payload_json = payload
        await session.commit()

    result = await run_compose_stage(project_id, 1)
    assert result is True, (await compose_stage(session_factory, project_id)).error

    export = (await compose_asset(session_factory, project_id)).payload_json["episodes"][0]
    assert (asset_root() / export["srt_path"]).read_text(encoding="utf-8") == ""
    metadata = await probe_video(asset_root() / export["clean_path"])
    assert all(stream["codec_type"] != "audio" for stream in metadata["streams"])


@pytest.mark.asyncio
async def test_special_subtitle_text_and_missing_clip(project_factory) -> None:
    project_id, session_factory = await prepare_compose(project_factory)
    async with session_factory() as session:
        dubbing = await session.scalar(
            select(ProjectAssetRecord).where(
                ProjectAssetRecord.project_id == project_id,
                ProjectAssetRecord.kind == "dubbing",
            )
        )
        payload = copy.deepcopy(dubbing.payload_json)
        payload["episodes"][0]["lines"][0]["text"] = "旧港：仓 库，'测试'"
        dubbing.payload_json = payload
        await session.commit()

    assert await run_compose_stage(project_id, 1) is True
    export = (await compose_asset(session_factory, project_id)).payload_json["episodes"][0]
    assert "旧港：仓 库，'测试'" in (asset_root() / export["srt_path"]).read_text(encoding="utf-8")

    render = await render_asset(session_factory, project_id)
    clip = render.payload_json["episodes"][0]["segments"][0]["cuts"][0]["clip_path"]
    (asset_root() / clip).unlink()
    assert await run_compose_stage(project_id, 1) is False
    assert (await compose_stage(session_factory, project_id)).status == "failed"
