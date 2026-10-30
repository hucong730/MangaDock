from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mangadock_api.database import get_db
from mangadock_api.models import CharacterImageRecord, CharacterRecord
from mangadock_api.queue import enqueue_task
from mangadock_api.routers.projects import get_project

router = APIRouter(prefix="/api/v1/projects", tags=["characters"])


@router.get("/{project_id}/characters")
async def list_characters(
    project_id: int,
    session: AsyncSession = Depends(get_db),
) -> dict:
    await get_project(session, project_id)
    characters = list(
        (
            await session.scalars(
                select(CharacterRecord).where(CharacterRecord.project_id == project_id)
            )
        ).all()
    )
    payload = {"characters": []}
    for character in characters:
        images = list(
            (
                await session.scalars(
                    select(CharacterImageRecord).where(
                        CharacterImageRecord.character_id == character.id
                    )
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
    return payload


@router.post("/{project_id}/characters/{character_id}/anchor-confirmation", status_code=202)
async def confirm_anchor(
    project_id: int,
    character_id: int,
    session: AsyncSession = Depends(get_db),
) -> dict:
    await get_project(session, project_id)
    character = await session.get(CharacterRecord, character_id)
    if character is None or character.project_id != project_id:
        raise HTTPException(status_code=404, detail="角色不存在")
    if character.anchor_confirmed:
        return {"status": "confirmed", "character_id": character_id}
    anchor = await session.scalar(
        select(CharacterImageRecord).where(
            CharacterImageRecord.character_id == character_id,
            CharacterImageRecord.label == "front_full",
        )
    )
    if anchor is None or anchor.status != "done":
        raise HTTPException(status_code=409, detail="正面全身锚点图尚未生成完成")
    enqueue_task("mangadock_worker.tasks.confirm_character_anchor", character_id)
    return {"status": "queued", "character_id": character_id}


@router.post("/{project_id}/character-images/{image_id}/regenerate", status_code=202)
async def regenerate_character_image(
    project_id: int,
    image_id: int,
    session: AsyncSession = Depends(get_db),
) -> dict:
    await get_project(session, project_id)
    result = await session.execute(
        select(CharacterImageRecord, CharacterRecord)
        .join(CharacterRecord, CharacterImageRecord.character_id == CharacterRecord.id)
        .where(
            CharacterImageRecord.id == image_id,
            CharacterRecord.project_id == project_id,
        )
    )
    owned = result.first()
    if owned is None:
        raise HTTPException(status_code=404, detail="图片不存在")
    image, character = owned
    if image.label != "front_full":
        anchor = await session.scalar(
            select(CharacterImageRecord).where(
                CharacterImageRecord.character_id == character.id,
                CharacterImageRecord.label == "front_full",
            )
        )
        if (
            not character.anchor_confirmed
            or anchor is None
            or anchor.status != "done"
        ):
            raise HTTPException(status_code=409, detail="请先确认已生成的正面全身锚点图")
    enqueue_task("mangadock_worker.tasks.regenerate_character_image", image_id)
    return {"status": "queued", "image_id": image_id}
