import copy

from sqlalchemy import select

from mangadock_core.pipeline.characters import generate_character_bible
from mangadock_core.schemas import CharacterSpec
from mangadock_persistence.models import (
    CharacterImageRecord,
    CharacterRecord,
    LLMProviderRecord,
    ProjectAssetRecord,
    ProjectProviderRouteRecord,
    ProjectRecord,
    ProjectStageRecord,
)
from mangadock_providers import ImageProviderError, ProviderError
from mangadock_worker.asset_paths import (
    absolute_asset_path,
    image_output_dir,
    relative_asset_path,
)
from mangadock_worker.celery_app import celery_app
from mangadock_worker.image_factory import image_provider_for_record
from mangadock_worker.pipeline_tasks import (
    new_session,
    run_async_task,
    set_stage,
)
from mangadock_worker.provider_factory import provider_for_record

VIEW_LABELS = ("avatar", "profile", "back", "detail")
VIEW_PROMPTS = {
    "avatar": "头像近景，保持身份与全部锚点特征",
    "profile": "90度侧脸，保持身份与全部锚点特征",
    "back": "背面全身，保持身份与全部锚点特征",
    "detail": "服装细节，保持锚点配色、材质和标志性配件",
}


async def get_stage(project_id: int, stage_name: str) -> ProjectStageRecord:
    async with new_session() as session:
        stage = await session.scalar(
            select(ProjectStageRecord).where(
                ProjectStageRecord.project_id == project_id,
                ProjectStageRecord.stage == stage_name,
            )
        )
        if stage is None:
            stage = ProjectStageRecord(project_id=project_id, stage=stage_name)
            session.add(stage)
            await session.commit()
        return stage


async def sync_character_asset(project_id: int) -> None:
    async with new_session() as session:
        characters = list(
            (
                await session.scalars(
                    select(CharacterRecord)
                    .where(CharacterRecord.project_id == project_id)
                    .order_by(CharacterRecord.id)
                )
            ).all()
        )
        payload = {"characters": []}
        for character in characters:
            images = list(
                (
                    await session.scalars(
                        select(CharacterImageRecord)
                        .where(CharacterImageRecord.character_id == character.id)
                        .order_by(CharacterImageRecord.id)
                    )
                ).all()
            )
            payload["characters"].append(
                {
                    "id": character.id,
                    "name": character.name,
                    "biography": character.biography,
                    "prompt_zh": character.prompt_zh,
                    "prompt_en": character.prompt_en,
                    "voice_prompt": character.voice_prompt,
                    "anchor_features": character.anchor_features,
                    "anchor_confirmed": character.anchor_confirmed,
                    "images": [
                        {
                            "id": image.id,
                            "label": image.label,
                            "status": image.status,
                            "path": image.path,
                            "width": image.width,
                            "height": image.height,
                            "format": image.format,
                            "workflow_id": image.workflow_id,
                            "error": image.error,
                        }
                        for image in images
                    ],
                }
            )
        asset = await session.scalar(
            select(ProjectAssetRecord).where(
                ProjectAssetRecord.project_id == project_id,
                ProjectAssetRecord.kind == "characters",
            )
        )
        if asset is None:
            asset = ProjectAssetRecord(
                project_id=project_id,
                kind="characters",
                payload_json=payload,
            )
            session.add(asset)
        else:
            asset.payload_json = payload
        await session.commit()


async def generate_image_record(
    image: CharacterImageRecord,
    character: CharacterRecord,
    workflow_id: str,
    prompt: str,
    reference_images: list[str],
) -> bool:
    async with new_session() as session:
        route = await session.scalar(
            select(ProjectProviderRouteRecord).where(
                ProjectProviderRouteRecord.project_id == character.project_id,
                ProjectProviderRouteRecord.role == "image",
            )
        )
        provider_record = (
            await session.get(LLMProviderRecord, route.provider_id)
            if route is not None
            else None
        )
    output_dir = image_output_dir(character.project_id)
    try:
        provider = image_provider_for_record(provider_record, workflow_id, output_dir)
        result = await provider.generate(
            prompt,
            [absolute_asset_path(path) for path in reference_images],
            (1024, 1024),
        )
    except (ImageProviderError, OSError, ValueError) as error:
        async with new_session() as session:
            current = await session.get(CharacterImageRecord, image.id)
            current.status = "failed"
            current.error = str(error)
            await session.commit()
        await sync_character_asset(character.project_id)
        return False

    async with new_session() as session:
        current = await session.get(CharacterImageRecord, image.id)
        current.status = "done"
        current.path = relative_asset_path(str(result.path))
        current.width = result.width
        current.height = result.height
        current.format = result.format
        current.workflow_id = result.workflow_id
        current.error = None
        await session.commit()
    await sync_character_asset(character.project_id)
    return True


async def finalize_characters_if_ready(project_id: int) -> bool:
    async with new_session() as session:
        characters = list(
            (
                await session.scalars(
                    select(CharacterRecord).where(CharacterRecord.project_id == project_id)
                )
            ).all()
        )
        images = list(
            (
                await session.scalars(
                    select(CharacterImageRecord)
                    .join(CharacterRecord)
                    .where(CharacterRecord.project_id == project_id)
                )
            ).all()
        )
    await sync_character_asset(project_id)
    if not characters or any(not character.anchor_confirmed for character in characters):
        await set_stage(
            project_id,
            "characters",
            status="waiting_confirmation",
            requires_attention=True,
        )
        return False
    if any(image.status == "failed" for image in images):
        await set_stage(
            project_id,
            "characters",
            status="failed",
            requires_attention=True,
            error="One or more character images failed",
        )
        return False
    if any(image.status in {"pending", "outdated"} for image in images):
        await set_stage(
            project_id,
            "characters",
            status="waiting_confirmation",
            requires_attention=True,
        )
        return False

    await set_stage(
        project_id,
        "characters",
        status="done",
        completed_items=len(images),
        total_items=len(images),
        error=None,
        requires_attention=False,
    )
    try:
        start_storyboard.delay(project_id)
    except Exception:
        await set_stage(
            project_id,
            "storyboard",
            status="failed",
            error="任务入队失败，请重试",
            requires_attention=True,
        )
        return False
    return True


async def run_character_stage(project_id: int) -> bool:
    async with new_session() as session:
        project = await session.get(ProjectRecord, project_id)
        provider_record = await session.get(LLMProviderRecord, project.provider_id)
        existing = list(
            (
                await session.scalars(
                    select(CharacterRecord).where(CharacterRecord.project_id == project_id)
                )
            ).all()
        )
    await get_stage(project_id, "characters")
    await get_stage(project_id, "storyboard")
    await set_stage(project_id, "characters", status="running", error=None)

    if not existing:
        try:
            from mangadock_core.schemas import Outline

            outline = Outline.model_validate(project.outline_json)
            llm = provider_for_record(provider_record)
            bible = await generate_character_bible(outline, llm)
        except (ProviderError, ValueError) as error:
            await set_stage(
                project_id,
                "characters",
                status="failed",
                error=str(error),
                requires_attention=True,
            )
            return False
        async with new_session() as session:
            for spec in bible.characters:
                session.add(
                    CharacterRecord(
                        project_id=project_id,
                        name=spec.name,
                        biography=spec.biography,
                        prompt_zh=spec.prompt_zh,
                        prompt_en=spec.prompt_en,
                        voice_prompt=spec.voice_prompt,
                        anchor_features=spec.anchor_features,
                    )
                )
            await session.commit()

    async with new_session() as session:
        characters = list(
            (
                await session.scalars(
                    select(CharacterRecord).where(CharacterRecord.project_id == project_id)
                )
            ).all()
        )
    for character in characters:
        async with new_session() as session:
            anchor = await session.scalar(
                select(CharacterImageRecord).where(
                    CharacterImageRecord.character_id == character.id,
                    CharacterImageRecord.label == "front_full",
                )
            )
            if anchor is None:
                anchor = CharacterImageRecord(
                    character_id=character.id,
                    label="front_full",
                    status="pending",
                )
                session.add(anchor)
                await session.commit()
        if anchor.status != "done":
            await generate_image_record(
                anchor,
                character,
                "character_anchor_v1",
                f"{character.prompt_zh}，正面全身，完整展示全部锚点特征",
                [],
            )
    await finalize_characters_if_ready(project_id)
    return True


@celery_app.task(name="mangadock_worker.tasks.stage_characters")
def stage_characters(project_id: int) -> bool:
    return run_async_task(run_character_stage(project_id))


async def confirm_character_anchor(character_id: int) -> bool:
    async with new_session() as session:
        character = await session.get(CharacterRecord, character_id)
        anchor = await session.scalar(
            select(CharacterImageRecord).where(
                CharacterImageRecord.character_id == character_id,
                CharacterImageRecord.label == "front_full",
            )
        )
        if anchor is None or anchor.status != "done":
            raise ValueError("Character anchor is not ready for confirmation")
        character.anchor_confirmed = True
        await session.commit()

    for label in VIEW_LABELS:
        async with new_session() as session:
            image = await session.scalar(
                select(CharacterImageRecord).where(
                    CharacterImageRecord.character_id == character_id,
                    CharacterImageRecord.label == label,
                )
            )
            if image is None:
                image = CharacterImageRecord(
                    character_id=character_id,
                    label=label,
                    status="pending",
                )
                session.add(image)
                await session.commit()
        if image.status != "done":
            await generate_image_record(
                image,
                character,
                "character_views_v1",
                f"{character.prompt_zh}，{VIEW_PROMPTS[label]}",
                [anchor.path],
            )
    await finalize_characters_if_ready(character.project_id)
    return True


@celery_app.task(name="mangadock_worker.tasks.confirm_character_anchor")
def confirm_anchor(character_id: int) -> bool:
    return run_async_task(confirm_character_anchor(character_id))


async def regenerate_character_image(image_id: int) -> bool:
    async with new_session() as session:
        image = await session.get(CharacterImageRecord, image_id)
        character = await session.get(CharacterRecord, image.character_id)
        anchor = await session.scalar(
            select(CharacterImageRecord).where(
                CharacterImageRecord.character_id == character.id,
                CharacterImageRecord.label == "front_full",
            )
        )
        if image.label != "front_full" and (
            not character.anchor_confirmed
            or anchor is None
            or anchor.status != "done"
        ):
            raise ValueError("Character anchor must be confirmed before generating views")
        if image.label == "front_full" and character.anchor_confirmed:
            character.anchor_confirmed = False
            other_images = list(
                (
                    await session.scalars(
                        select(CharacterImageRecord).where(
                            CharacterImageRecord.character_id == character.id,
                            CharacterImageRecord.label != "front_full",
                        )
                    )
                ).all()
            )
            for other in other_images:
                other.status = "outdated"
            storyboard_asset = await session.scalar(
                select(ProjectAssetRecord).where(
                    ProjectAssetRecord.project_id == character.project_id,
                    ProjectAssetRecord.kind == "storyboard",
                )
            )
            if storyboard_asset is not None:
                payload = copy.deepcopy(storyboard_asset.payload_json)
                for episode in payload["episodes"]:
                    for segment in episode["segments"]:
                        for cut in segment["cuts"]:
                            cut["keyframe_image"] = None
                storyboard_asset.payload_json = payload
            storyboard_stage = await session.scalar(
                select(ProjectStageRecord).where(
                    ProjectStageRecord.project_id == character.project_id,
                    ProjectStageRecord.stage == "storyboard",
                )
            )
            if storyboard_stage is not None:
                storyboard_stage.status = "pending"
                storyboard_stage.completed_items = 0
                storyboard_stage.attempt_count = 0
                storyboard_stage.error = None
                storyboard_stage.requires_attention = False
            await session.commit()

    if image.label == "front_full":
        workflow_id = "character_anchor_v1"
        prompt = f"{character.prompt_zh}，正面全身，完整展示全部锚点特征"
        references = []
    else:
        workflow_id = "character_views_v1"
        prompt = f"{character.prompt_zh}，{VIEW_PROMPTS[image.label]}"
        references = [anchor.path]
    success = await generate_image_record(
        image,
        character,
        workflow_id,
        prompt,
        references,
    )
    if not success:
        return False
    await finalize_characters_if_ready(character.project_id)
    return True


@celery_app.task(name="mangadock_worker.tasks.regenerate_character_image")
def regenerate_image(image_id: int) -> bool:
    return run_async_task(regenerate_character_image(image_id))


@celery_app.task(name="mangadock_worker.tasks.stage_storyboard")
def start_storyboard(project_id: int) -> bool:
    from mangadock_worker.storyboard_tasks import run_storyboard_stage

    return run_async_task(run_storyboard_stage(project_id))
