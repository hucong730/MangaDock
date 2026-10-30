from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mangadock_api.database import get_db
from mangadock_api.models import ProjectAssetRecord
from mangadock_api.routers.projects import get_project

router = APIRouter(prefix="/api/v1/projects", tags=["storyboard"])


@router.get("/{project_id}/storyboard")
async def read_storyboard(
    project_id: int,
    session: AsyncSession = Depends(get_db),
) -> dict:
    await get_project(session, project_id)
    asset = await session.scalar(
        select(ProjectAssetRecord).where(
            ProjectAssetRecord.project_id == project_id,
            ProjectAssetRecord.kind == "storyboard",
        )
    )
    if asset is None:
        raise HTTPException(status_code=409, detail="Storyboard 尚未生成")
    return asset.payload_json
