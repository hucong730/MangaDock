import os

from mangadock_core.fingerprints import dependency_fingerprint
from mangadock_core.pipeline.subtitles import render_subtitles
from mangadock_core.schemas import Compose, Dubbing
from mangadock_providers.media import MediaToolError
from mangadock_worker.asset_paths import asset_root, relative_asset_path
from mangadock_worker.asset_store import (
    asset_output_dir,
    get_project_asset,
    upsert_project_asset,
)
from mangadock_worker.celery_app import celery_app
from mangadock_worker.character_tasks import get_stage
from mangadock_worker.media_processing import compose_episode_media
from mangadock_worker.pipeline_tasks import new_session, run_async_task, set_stage


def compose_fingerprint(render_episode, dubbing_episode) -> str:
    return dependency_fingerprint(
        {
            "clips": render_episode["segments"],
            "dubbing": dubbing_episode,
            "subtitle": {
                "font": os.getenv("SUBTITLE_FONT", "Noto Sans CJK SC"),
                "size": os.getenv("SUBTITLE_FONT_SIZE", "24"),
                "alignment": os.getenv("SUBTITLE_ALIGNMENT", "2"),
                "outline": os.getenv("SUBTITLE_OUTLINE", "2"),
            },
        }
    )


async def run_compose_stage(project_id: int, episode: int) -> bool:
    await get_stage(project_id, "compose")
    async with new_session() as session:
        render_asset = await get_project_asset(session, project_id, "render")
        dubbing_asset = await get_project_asset(session, project_id, "dubbing")
        compose_asset = await get_project_asset(session, project_id, "compose")
    if not render_asset or not dubbing_asset:
        await set_stage(
            project_id,
            "compose",
            status="failed",
            error="Render and dubbing must be ready",
            requires_attention=True,
        )
        return False
    render_episode = next(
        item for item in render_asset.payload_json["episodes"] if item["episode"] == episode
    )
    dubbing_episode = next(
        item for item in dubbing_asset.payload_json["episodes"] if item["episode"] == episode
    )
    render_cuts = [
        cut for segment in render_episode["segments"] for cut in segment["cuts"]
    ]
    if any(
        cut["status"] != "done" or not (asset_root() / cut["clip_path"]).is_file()
        for cut in render_cuts
    ):
        await set_stage(
            project_id,
            "compose",
            status="failed",
            error="One or more rendered clips are missing",
            requires_attention=True,
        )
        return False
    fingerprint = compose_fingerprint(render_episode, dubbing_episode)
    if compose_asset is not None:
        existing = next(
            (
                item for item in compose_asset.payload_json["episodes"]
                if item["episode"] == episode
            ),
            None,
        )
        if existing and existing.get("source_fingerprint") == fingerprint and all(
            (asset_root() / existing[field]).is_file()
            for field in ("burned_path", "clean_path", "srt_path", "vtt_path")
        ):
            return True

    await set_stage(project_id, "compose", status="running", error=None, requires_attention=False)
    try:
        dubbing = Dubbing(episodes=[dubbing_episode])
        srt, vtt = render_subtitles(dubbing, episode)
        lines = []
        for line in dubbing_episode["lines"]:
            value = dict(line)
            value["absolute_audio_path"] = asset_root() / line["audio_path"]
            lines.append(value)
        result = await compose_episode_media(
            [
                (asset_root() / cut["clip_path"], cut["duration_s"])
                for cut in render_cuts
            ],
            lines,
            asset_root() / "projects" / str(project_id) / "exports" / f"episode_{episode}",
            episode,
            srt,
            vtt,
        )
        export = {
            "episode": episode,
            "status": "done",
            "burned_path": relative_asset_path(str(result["burned_path"])),
            "clean_path": relative_asset_path(str(result["clean_path"])),
            "srt_path": relative_asset_path(str(result["srt_path"])),
            "vtt_path": relative_asset_path(str(result["vtt_path"])),
            "duration_s": result["duration_s"],
            "width": 1920,
            "height": 1080,
            "source_fingerprint": fingerprint,
            "error": None,
        }
        other_episodes = []
        if compose_asset is not None:
            other_episodes = [
                item for item in compose_asset.payload_json["episodes"] if item["episode"] != episode
            ]
        payload = Compose(episodes=[*other_episodes, export]).model_dump(mode="json")
        async with new_session() as session:
            await upsert_project_asset(session, project_id, "compose", payload)
    except (MediaToolError, OSError, ValueError) as error:
        await set_stage(
            project_id,
            "compose",
            status="failed",
            error=str(error),
            requires_attention=True,
        )
        return False
    await set_stage(
        project_id,
        "compose",
        status="done",
        completed_items=1,
        total_items=1,
        error=None,
        requires_attention=False,
    )
    return True


@celery_app.task(name="mangadock_worker.tasks.stage_compose")
def stage_compose(project_id: int, episode: int) -> bool:
    return run_async_task(run_compose_stage(project_id, episode))
