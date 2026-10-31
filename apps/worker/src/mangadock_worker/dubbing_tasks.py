import os

from mangadock_core.fingerprints import dependency_fingerprint
from mangadock_core.pipeline.dubbing import (
    apply_dubbing_timing,
    build_dubbing_plan,
    validate_dubbing,
)
from mangadock_core.schemas import Dubbing, Script, Storyboard
from mangadock_persistence.models import CharacterRecord, ProjectRecord
from mangadock_providers import TTSProviderError
from mangadock_worker.asset_paths import asset_root, relative_asset_path
from mangadock_worker.asset_store import (
    asset_output_dir,
    get_project_asset,
    upsert_project_asset,
)
from mangadock_worker.celery_app import celery_app
from mangadock_worker.character_tasks import get_stage
from mangadock_worker.pipeline_tasks import new_session, run_async_task, set_stage
from mangadock_worker.tts_factory import tts_for_project
from sqlalchemy import select


def enqueue_render(project_id: int, episode: int) -> None:
    from mangadock_worker.render_tasks import start_render

    start_render.delay(project_id, episode)


def tts_settings(mode: str) -> dict:
    return {
        "mode": mode,
        "voice_map": os.getenv("EDGE_TTS_VOICE_MAP", "{}"),
        "default_voice": os.getenv("EDGE_TTS_DEFAULT_VOICE", "zh-CN-XiaoxiaoNeural"),
        "rate": os.getenv("EDGE_TTS_RATE", "+0%"),
        "pitch": os.getenv("EDGE_TTS_PITCH", "+0Hz"),
    }


def line_fingerprint(line, characters, mode: str) -> str:
    character = next(item for item in characters if item.name == line.character)
    return dependency_fingerprint(
        {
            "line": line,
            "voice": character.voice_prompt,
            "tts": tts_settings(mode),
        }
    )


def valid_dubbing_episode(asset, episode: int, fingerprint: str, script, board) -> bool:
    if asset is None:
        return False
    episode_asset = next(
        (item for item in asset.payload_json["episodes"] if item["episode"] == episode),
        None,
    )
    if not episode_asset or episode_asset.get("source_fingerprint") != fingerprint:
        return False
    if any(line["status"] != "done" for line in episode_asset["lines"]):
        return False
    if any(not (asset_root() / line["audio_path"]).is_file() for line in episode_asset["lines"]):
        return False
    try:
        validate_dubbing({"episodes": [episode_asset]}, script, board, episode)
    except ValueError:
        return False
    return True


async def run_dubbing_stage(project_id: int, episode: int) -> bool:
    await get_stage(project_id, "dubbing")
    await get_stage(project_id, "render")
    await get_stage(project_id, "compose")
    async with new_session() as session:
        project = await session.get(ProjectRecord, project_id)
        storyboard_asset = await get_project_asset(session, project_id, "storyboard")
        dubbing_asset = await get_project_asset(session, project_id, "dubbing")
        characters = list(
            (
                await session.scalars(
                    select(CharacterRecord).where(CharacterRecord.project_id == project_id)
                )
            ).all()
        )
    if not project.script_json or not storyboard_asset:
        await set_stage(project_id, "dubbing", status="failed", error="Storyboard is not ready", requires_attention=True)
        return False
    script = Script.model_validate(project.script_json)
    storyboard = Storyboard.model_validate(storyboard_asset.payload_json)
    script_episode = next(item for item in script.episodes if item.episode == episode)
    board_episode = next(item for item in storyboard.episodes if item.episode == episode)
    mode = os.getenv("MANGADOCK_TTS_MODE", "fake").lower()
    lines = build_dubbing_plan(script, board_episode, episode)
    line_fingerprints = {
        line.line_id: line_fingerprint(line, characters, mode) for line in lines
    }
    fingerprint = dependency_fingerprint(line_fingerprints)
    other_episodes = []
    existing_lines = {}
    if dubbing_asset is not None:
        other_episodes = [
            item for item in dubbing_asset.payload_json["episodes"] if item["episode"] != episode
        ]
        existing = next(
            (
                item for item in dubbing_asset.payload_json["episodes"]
                if item["episode"] == episode
            ),
            None,
        )
        if existing:
            existing_lines = {line["line_id"]: line for line in existing["lines"]}
    if valid_dubbing_episode(
        dubbing_asset, episode, fingerprint, script, storyboard
    ):
        enqueue_render(project_id, episode)
        return True
    output_dir = asset_output_dir(project_id, "audio", f"episode_{episode}")
    provider = tts_for_project(project_id, episode, output_dir)
    await set_stage(
        project_id,
        "dubbing",
        status="running",
        completed_items=0,
        total_items=len(lines),
        error=None,
        requires_attention=False,
    )

    async def persist(completed: int) -> None:
        episode_payload = {
            "episode": episode,
            "source_fingerprint": fingerprint,
            "lines": [line.model_dump(mode="json") for line in lines],
        }
        payload = {"episodes": [*other_episodes, episode_payload]}
        async with new_session() as session:
            await upsert_project_asset(session, project_id, "dubbing", payload)
        await set_stage(
            project_id,
            "dubbing",
            status="running",
            completed_items=completed,
            total_items=len(lines),
        )

    completed = 0
    for line in lines:
        line.source_fingerprint = line_fingerprints[line.line_id]
        existing = existing_lines.get(line.line_id)
        if (
            existing
            and existing["status"] == "done"
            and existing.get("source_fingerprint") == line.source_fingerprint
            and (asset_root() / existing["audio_path"]).is_file()
        ):
            for field in (
                "audio_path",
                "start_s",
                "duration_s",
                "end_s",
                "status",
                "error",
            ):
                setattr(line, field, existing[field])
            completed += 1
            continue
        try:
            line.status = "running"
            result = await provider.synthesize(
                line.text,
                next(item.voice_prompt for item in characters if item.name == line.character),
                line.emotion,
            )
            line.audio_path = relative_asset_path(str(result.path))
            line.duration_s = result.duration_s
            line.status = "done"
            line.error = None
            apply_dubbing_timing(lines, board_episode)
        except (TTSProviderError, OSError, ValueError) as error:
            line.status = "failed"
            line.error = str(error)
            apply_dubbing_timing(lines, board_episode)
        completed += 1
        await persist(completed)

    await persist(completed)
    if any(line.status == "failed" for line in lines):
        await set_stage(
            project_id,
            "dubbing",
            status="failed",
            completed_items=completed,
            total_items=len(lines),
            error="One or more dubbing lines failed",
            requires_attention=True,
        )
        return False
    await set_stage(
        project_id,
        "dubbing",
        status="done",
        completed_items=completed,
        total_items=len(lines),
        error=None,
        requires_attention=False,
    )
    try:
        enqueue_render(project_id, episode)
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


@celery_app.task(name="mangadock_worker.tasks.stage_dubbing")
def stage_dubbing(project_id: int, episode: int) -> bool:
    return run_async_task(run_dubbing_stage(project_id, episode))
