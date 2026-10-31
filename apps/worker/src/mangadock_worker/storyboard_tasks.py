from pydantic import ValidationError
from sqlalchemy import select

from mangadock_core.pipeline.storyboard import generate_storyboard
from mangadock_core.schemas import (
    CharacterBible,
    CharacterSpec,
    KeyframeImage,
    Script,
    Storyboard,
)
from mangadock_core.schemas.storyboard import validate_storyboard
from mangadock_persistence.models import (
    CharacterImageRecord,
    CharacterRecord,
    LLMProviderRecord,
    ProjectAssetRecord,
    ProjectRecord,
    ProjectProviderRouteRecord,
)
from mangadock_providers import ImageProviderError, ProviderError
from mangadock_worker.asset_paths import (
    absolute_asset_path,
    image_output_dir,
    relative_asset_path,
)
from mangadock_worker.celery_app import celery_app
from mangadock_worker.character_tasks import get_stage, invalidate_generated_media
from mangadock_worker.image_factory import image_provider_for_record
from mangadock_worker.pipeline_tasks import new_session, run_async_task, set_stage
from mangadock_worker.provider_factory import provider_for_record


async def load_bible(project_id: int) -> CharacterBible:
    async with new_session() as session:
        records = list(
            (
                await session.scalars(
                    select(CharacterRecord).where(CharacterRecord.project_id == project_id)
                )
            ).all()
        )
    return CharacterBible(
        characters=[
            CharacterSpec(
                name=record.name,
                biography=record.biography,
                prompt_zh=record.prompt_zh,
                prompt_en=record.prompt_en,
                voice_prompt=record.voice_prompt,
                anchor_features=record.anchor_features,
            )
            for record in records
        ]
    )


async def save_storyboard_asset(project_id: int, board: Storyboard) -> None:
    payload = board.model_dump(mode="json")
    async with new_session() as session:
        asset = await session.scalar(
            select(ProjectAssetRecord).where(
                ProjectAssetRecord.project_id == project_id,
                ProjectAssetRecord.kind == "storyboard",
            )
        )
        if asset is None:
            asset = ProjectAssetRecord(
                project_id=project_id,
                kind="storyboard",
                payload_json=payload,
            )
            session.add(asset)
        else:
            asset.payload_json = payload
        await session.commit()


async def generate_keyframe(
    project_id: int,
    board_episode: int,
    segment_index: int,
    cut,
    characters: list[CharacterRecord],
) -> bool:
    async with new_session() as session:
        route = await session.scalar(
            select(ProjectProviderRouteRecord).where(
                ProjectProviderRouteRecord.project_id == project_id,
                ProjectProviderRouteRecord.role == "image",
            )
        )
        provider_record = (
            await session.get(LLMProviderRecord, route.provider_id)
            if route is not None
            else None
        )
    output_dir = image_output_dir(project_id, "storyboard")
    async with new_session() as session:
        anchor_images = list(
            (
                await session.scalars(
                    select(CharacterImageRecord).where(
                        CharacterImageRecord.character_id.in_(
                            [character.id for character in characters]
                        ),
                        CharacterImageRecord.label == "front_full",
                    )
                )
            ).all()
        )
    references = [
        absolute_asset_path(
            next(
                image
                for image in anchor_images
                if image.character_id == next(
                    character for character in characters if character.name == name
                ).id
            ).path
        )
        for name in cut.characters
    ]
    try:
        provider = image_provider_for_record(
            provider_record,
            "storyboard_keyframe_v1",
            output_dir,
        )
        result = await provider.generate(
            f"{cut.prompt}；运镜：{cut.camera}",
            references,
            (1024, 1024),
        )
    except (ImageProviderError, OSError, ValueError):
        return False
    cut.keyframe_image = KeyframeImage(
        path=relative_asset_path(str(result.path)),
        width=result.width,
        height=result.height,
        format=result.format,
        workflow_id=result.workflow_id,
    )
    return True


async def run_storyboard_stage(project_id: int) -> bool:
    await get_stage(project_id, "storyboard")
    await set_stage(project_id, "storyboard", status="running", error=None)
    async with new_session() as session:
        project = await session.get(ProjectRecord, project_id)
        provider_record = await session.get(LLMProviderRecord, project.provider_id)
        characters = list(
            (
                await session.scalars(
                    select(CharacterRecord).where(CharacterRecord.project_id == project_id)
                )
            ).all()
        )
        asset = await session.scalar(
            select(ProjectAssetRecord).where(
                ProjectAssetRecord.project_id == project_id,
                ProjectAssetRecord.kind == "storyboard",
            )
        )
    if not characters or any(not character.anchor_confirmed for character in characters):
        await set_stage(
            project_id,
            "storyboard",
            status="failed",
            error="Character anchors are not confirmed",
            requires_attention=True,
        )
        return False

    script = Script.model_validate(project.script_json)
    bible = await load_bible(project_id)
    board = None
    if asset is not None:
        try:
            board = validate_storyboard(asset.payload_json, script, bible)
        except (ValidationError, ValueError):
            board = None

    generation_attempt = 1
    if board is None:
        for attempt in range(1, 3):
            try:
                llm = provider_for_record(provider_record)
                board = await generate_storyboard(script, bible, llm)
                generation_attempt = attempt
                break
            except (ProviderError, ValidationError, ValueError) as error:
                await set_stage(
                    project_id,
                    "storyboard",
                    status="running",
                    attempt_count=attempt,
                    error=str(error),
                )
        if board is None:
            await set_stage(
                project_id,
                "storyboard",
                status="failed",
                error="Storyboard validation failed twice",
                requires_attention=True,
            )
            return False

    await save_storyboard_asset(project_id, board)
    total = sum(
        len(segment.cuts)
        for episode in board.episodes
        for segment in episode.segments
    )
    completed = 0
    failed = 0
    for episode in board.episodes:
        for segment in episode.segments:
            for cut in segment.cuts:
                if cut.keyframe_image is not None:
                    completed += 1
                    continue
                success = await generate_keyframe(
                    project_id,
                    episode.episode,
                    segment.index,
                    cut,
                    characters,
                )
                if success:
                    completed += 1
                else:
                    failed += 1
                await save_storyboard_asset(project_id, board)
                await set_stage(
                    project_id,
                    "storyboard",
                    status="running",
                    completed_items=completed,
                    total_items=total,
                )

    if failed:
        await set_stage(
            project_id,
            "storyboard",
            status="failed",
            completed_items=completed,
            total_items=total,
            error="One or more keyframes failed",
            requires_attention=True,
        )
        return False
    await set_stage(
        project_id,
        "storyboard",
        status="done",
        attempt_count=generation_attempt,
        completed_items=completed,
        total_items=total,
        error=None,
        requires_attention=False,
    )
    async with new_session() as session:
        await invalidate_generated_media(session, project_id)
        await session.commit()
    return True


@celery_app.task(name="mangadock_worker.tasks.generate_storyboard")
def generate_storyboard_task(project_id: int) -> bool:
    return run_async_task(run_storyboard_stage(project_id))
