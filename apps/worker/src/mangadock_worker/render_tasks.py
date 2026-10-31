import asyncio
import copy
import os

from celery import chord, group
from sqlalchemy import select

from mangadock_core.fingerprints import dependency_fingerprint
from mangadock_core.schemas import Render, Storyboard
from mangadock_persistence.models import (
    ProjectAssetRecord,
    ProjectVideoRouteRecord,
    VideoProviderRecord,
)
from mangadock_providers import VideoProviderError
from mangadock_worker.asset_paths import asset_root, relative_asset_path
from mangadock_worker.asset_store import (
    asset_output_dir,
    get_project_asset,
    upsert_project_asset,
)
from mangadock_worker.celery_app import celery_app
from mangadock_worker.character_tasks import get_stage
from mangadock_worker.pipeline_tasks import new_session, run_async_task, set_stage
from mangadock_worker.video_factory import (
    build_video_prompt,
    video_for_record,
    video_mode,
)

SEMAPHORES = {}


def enqueue_compose(project_id: int, episode: int) -> None:
    from mangadock_worker.compose_tasks import stage_compose

    stage_compose.delay(project_id, episode)


async def resolve_video_record(session, project_id: int, episode: int, segment: int):
    route = await session.scalar(
        select(ProjectVideoRouteRecord).where(
            ProjectVideoRouteRecord.project_id == project_id,
            ProjectVideoRouteRecord.episode == episode,
            ProjectVideoRouteRecord.segment_index == segment,
        )
    )
    if route is None:
        route = await session.scalar(
            select(ProjectVideoRouteRecord).where(
                ProjectVideoRouteRecord.project_id == project_id,
                ProjectVideoRouteRecord.episode == 0,
                ProjectVideoRouteRecord.segment_index == 0,
            )
        )
    if route is None:
        return None
    return await session.get(VideoProviderRecord, route.video_provider_id)


def cut_fingerprint(cut, dubbing_lines, record, mode: str) -> str:
    referenced = [
        {
            "scene": ref.scene,
            "order": ref.order,
            "audio": next(
                (
                    {
                        "duration_s": line["duration_s"],
                        "audio_path": line["audio_path"],
                    }
                    for line in dubbing_lines
                    if line["scene"] == ref.scene and line["order"] == ref.order
                ),
                None,
            ),
        }
        for ref in cut.line_refs
    ]
    provider = None
    if record is not None:
        provider = {
            "id": record.id,
            "kind": record.kind,
            "base_url": record.base_url,
            "model": record.model,
            "config": record.config_json,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }
    return dependency_fingerprint(
        {"cut": cut, "dubbing": referenced, "provider": provider, "mode": mode}
    )


async def ensure_render_episode(
    project_id: int,
    episode: int,
    only_cut: int | None = None,
):
    async with new_session() as session:
        storyboard_asset = await get_project_asset(session, project_id, "storyboard")
        dubbing_asset = await get_project_asset(session, project_id, "dubbing")
        render_asset = await get_project_asset(session, project_id, "render")
        if not storyboard_asset or not dubbing_asset:
            raise ValueError("Storyboard and dubbing must be ready")
        storyboard = Storyboard.model_validate(storyboard_asset.payload_json)
        board = next(item for item in storyboard.episodes if item.episode == episode)
        dubbing_episode = next(
            item for item in dubbing_asset.payload_json["episodes"] if item["episode"] == episode
        )
        if any(line["status"] != "done" for line in dubbing_episode["lines"]):
            raise ValueError("Dubbing contains failed lines")
        existing_episode = None
        other_episodes = []
        if render_asset is not None:
            other_episodes = [
                item for item in render_asset.payload_json["episodes"] if item["episode"] != episode
            ]
            existing_episode = next(
                (
                    item for item in render_asset.payload_json["episodes"]
                    if item["episode"] == episode
                ),
                None,
            )
        existing_cuts = {}
        if existing_episode:
            existing_cuts = {
                (segment["index"], cut["index"]): cut
                for segment in existing_episode["segments"]
                for cut in segment["cuts"]
            }
        segments = []
        for segment in board.segments:
            cuts = []
            for cut in segment.cuts:
                record = await resolve_video_record(
                    session, project_id, episode, segment.index
                )
                fingerprint = cut_fingerprint(
                    cut, dubbing_episode["lines"], record, video_mode()
                )
                previous = existing_cuts.get((segment.index, cut.index), {})
                preserve_failed = (
                    only_cut is not None
                    and cut.index != only_cut
                    and previous.get("status") == "failed"
                )
                reusable = (
                    previous.get("status") == "done"
                    and previous.get("source_fingerprint") == fingerprint
                    and previous.get("clip_path")
                    and (asset_root() / previous["clip_path"]).is_file()
                )
                cuts.append(
                    {
                        "index": cut.index,
                        "duration_s": cut.duration_s,
                        "status": previous.get("status") if preserve_failed else "done" if reusable else "pending",
                        "attempt_count": previous.get("attempt_count", 0)
                        if previous.get("source_fingerprint") == fingerprint
                        else 0,
                        "provider_id": record.id if record is not None else None,
                        "clip_path": previous.get("clip_path")
                        if preserve_failed or reusable
                        else None,
                        "source_duration_s": previous.get("source_duration_s")
                        if preserve_failed or reusable
                        else None,
                        "source_fingerprint": fingerprint,
                        "error": previous.get("error") if preserve_failed else None,
                    }
                )
            segments.append({"index": segment.index, "cuts": cuts})
        episode_payload = {"episode": episode, "segments": segments}
        payload = Render(episodes=[*other_episodes, episode_payload]).model_dump(mode="json")
        await upsert_project_asset(session, project_id, "render", payload)
        return storyboard, dubbing_episode, payload


async def persist_render(project_id: int, payload: dict, status="running") -> None:
    cuts = [
        cut
        for episode in payload["episodes"]
        for segment in episode["segments"]
        for cut in segment["cuts"]
    ]
    async with new_session() as session:
        await upsert_project_asset(session, project_id, "render", payload)
    await set_stage(
        project_id,
        "render",
        status=status,
        completed_items=sum(cut["status"] == "done" for cut in cuts),
        total_items=len(cuts),
        error="One or more video clips failed" if status == "failed" else None,
        requires_attention=status == "failed",
    )


async def persist_cut(
    project_id: int,
    episode: int,
    segment_index: int,
    cut_index: int,
    values: dict,
    dubbing_lines: list[dict],
    expected_fingerprint: str | None = None,
) -> bool:
    valid = True
    async with new_session() as session:
        storyboard_asset = await session.scalar(
            select(ProjectAssetRecord)
            .where(
                ProjectAssetRecord.project_id == project_id,
                ProjectAssetRecord.kind == "storyboard",
            )
            .with_for_update()
        )
        asset = await get_project_asset(session, project_id, "render")
        values = dict(values)
        if expected_fingerprint is not None:
            storyboard = Storyboard.model_validate(storyboard_asset.payload_json)
            current_cut = next(
                item
                for board in storyboard.episodes
                if board.episode == episode
                for segment in board.segments
                if segment.index == segment_index
                for item in segment.cuts
                if item.index == cut_index
            )
            record = await resolve_video_record(
                session, project_id, episode, segment_index
            )
            current = cut_fingerprint(
                current_cut, dubbing_lines, record, video_mode()
            )
            if current != expected_fingerprint:
                valid = False
                values.update(
                    {
                        "status": "outdated",
                        "clip_path": None,
                        "error": "Render inputs changed while generating",
                    }
                )
        payload = copy.deepcopy(asset.payload_json)
        target = next(
            cut
            for episode_asset in payload["episodes"]
            if episode_asset["episode"] == episode
            for segment in episode_asset["segments"]
            if segment["index"] == segment_index
            for cut in segment["cuts"]
            if cut["index"] == cut_index
        )
        target.update(values)
        await upsert_project_asset(session, project_id, "render", payload)
    cuts = [
        cut
        for episode_asset in payload["episodes"]
        for segment in episode_asset["segments"]
        for cut in segment["cuts"]
    ]
    await set_stage(
        project_id,
        "render",
        status="running",
        completed_items=sum(cut["status"] == "done" for cut in cuts),
        total_items=len(cuts),
    )
    return valid


def provider_semaphore(record):
    key = record.id if record is not None else 0
    configured = record.config_json.get("max_concurrency", 2) if record is not None else 2
    limit = min(int(configured), int(os.getenv("VIDEO_MAX_CONCURRENCY", "2")))
    if key not in SEMAPHORES or SEMAPHORES[key][0] != limit:
        SEMAPHORES[key] = (limit, asyncio.Semaphore(limit))
    return SEMAPHORES[key][1]


async def run_render_segment(
    project_id: int,
    episode: int,
    segment_index: int,
    only_cut: int | None = None,
) -> bool:
    await get_stage(project_id, "render")
    try:
        storyboard, dubbing_episode, payload = await ensure_render_episode(
            project_id, episode, only_cut
        )
    except ValueError as error:
        await set_stage(
            project_id,
            "render",
            status="failed",
            error=str(error),
            requires_attention=True,
        )
        return False
    board = next(item for item in storyboard.episodes if item.episode == episode)
    board_segment = next(item for item in board.segments if item.index == segment_index)
    render_episode = next(item for item in payload["episodes"] if item["episode"] == episode)
    render_segment = next(
        item for item in render_episode["segments"] if item["index"] == segment_index
    )
    segment_payload = board_segment.model_dump()
    persist_lock = asyncio.Lock()

    async def render_cut(cut, render_clip: dict) -> bool:
        if render_clip["status"] == "done" and render_clip.get("clip_path"):
            return True
        output_dir = asset_output_dir(
            project_id, "clips", f"episode_{episode}", f"segment_{segment_index}"
        )
        async with new_session() as session:
            record = await resolve_video_record(
                session, project_id, episode, segment_index
            )
        fingerprint = render_clip["source_fingerprint"]
        for _ in range(2):
            render_clip["attempt_count"] += 1
            render_clip["status"] = "running"
            try:
                if record is not None and not record.enabled:
                    raise ValueError("Video provider is disabled")
                async with provider_semaphore(record):
                    provider = video_for_record(record, output_dir)
                    result = await provider.generate(
                        str(asset_root() / cut.keyframe_image.path),
                        build_video_prompt(record, segment_payload, cut.index),
                        cut.duration_s,
                        record.config_json if record is not None else {},
                    )
                render_clip["status"] = "done"
                render_clip["clip_path"] = relative_asset_path(str(result.path))
                render_clip["source_duration_s"] = result.source_duration_s
                render_clip["error"] = None
                async with persist_lock:
                    return await persist_cut(
                        project_id,
                        episode,
                        segment_index,
                        cut.index,
                        render_clip,
                        dubbing_episode["lines"],
                        fingerprint,
                    )
            except (VideoProviderError, OSError, ValueError) as error:
                render_clip["error"] = str(error)
        render_clip["status"] = "failed"
        render_clip["clip_path"] = None
        async with persist_lock:
            await persist_cut(
                project_id,
                episode,
                segment_index,
                cut.index,
                render_clip,
                dubbing_episode["lines"],
            )
        return False

    targets = [
        (cut, clip)
        for cut, clip in zip(board_segment.cuts, render_segment["cuts"])
        if only_cut is None or cut.index == only_cut
    ]
    results = await asyncio.gather(
        *(render_cut(cut, clip) for cut, clip in targets)
    )
    return all(results)


async def run_finish_render(project_id: int, episode: int) -> bool:
    async with new_session() as session:
        asset = await get_project_asset(session, project_id, "render")
    if asset is None:
        return False
    episode_asset = next(
        item for item in asset.payload_json["episodes"] if item["episode"] == episode
    )
    cuts = [
        cut for segment in episode_asset["segments"] for cut in segment["cuts"]
    ]
    if any(cut["status"] != "done" for cut in cuts):
        await persist_render(project_id, asset.payload_json, status="failed")
        return False
    await persist_render(project_id, asset.payload_json, status="done")
    try:
        enqueue_compose(project_id, episode)
    except Exception:
        await set_stage(
            project_id,
            "render",
            status="failed",
            error="任务入队失败，请重试",
            requires_attention=True,
        )
        return False
    return True


async def retry_render_cut(
    project_id: int,
    episode: int,
    segment_index: int,
    cut_index: int,
) -> bool:
    async with new_session() as session:
        asset = await get_project_asset(session, project_id, "render")
        if asset is None:
            return False
        payload = asset.payload_json
        cut = next(
            cut
            for episode_asset in payload["episodes"]
            if episode_asset["episode"] == episode
            for segment in episode_asset["segments"]
            if segment["index"] == segment_index
            for cut in segment["cuts"]
            if cut["index"] == cut_index
        )
        cut["status"] = "pending"
        cut["attempt_count"] = 0
        cut["error"] = None
        await upsert_project_asset(session, project_id, "render", payload)
    if not await run_render_segment(project_id, episode, segment_index, cut_index):
        return False
    return await run_finish_render(project_id, episode)


@celery_app.task(name="mangadock_worker.tasks.start_render")
def start_render(project_id: int, episode: int) -> None:
    async def prepare():
        storyboard_asset = None
        async with new_session() as session:
            storyboard_asset = await get_project_asset(session, project_id, "storyboard")
        board = Storyboard.model_validate(storyboard_asset.payload_json)
        for segment in next(item for item in board.episodes if item.episode == episode).segments:
            await ensure_render_episode(project_id, episode)
        return [segment.index for segment in next(item for item in board.episodes if item.episode == episode).segments]

    try:
        segment_indices = run_async_task(prepare())
        chord(
            group(
                [render_segment.s(project_id, episode, index) for index in segment_indices]
            ),
            finish_render.si(project_id, episode),
        ).delay()
    except Exception:
        run_async_task(
            set_stage(
                project_id,
                "render",
                status="failed",
                error="任务入队失败，请重试",
                requires_attention=True,
            )
        )


@celery_app.task(name="mangadock_worker.tasks.render_segment")
def render_segment(project_id: int, episode: int, segment_index: int) -> bool:
    return run_async_task(run_render_segment(project_id, episode, segment_index))


@celery_app.task(name="mangadock_worker.tasks.finish_render")
def finish_render(project_id: int, episode: int) -> bool:
    return run_async_task(run_finish_render(project_id, episode))


@celery_app.task(name="mangadock_worker.tasks.retry_render_cut")
def retry_cut(project_id: int, episode: int, segment_index: int, cut_index: int) -> bool:
    return run_async_task(retry_render_cut(project_id, episode, segment_index, cut_index))
