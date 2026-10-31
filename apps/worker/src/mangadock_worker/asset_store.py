from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mangadock_persistence.models import ProjectAssetRecord
from mangadock_worker.asset_paths import asset_root


def asset_output_dir(project_id: int, *parts: str) -> str:
    path = asset_root() / "projects" / str(project_id)
    for part in parts:
        path /= part
    return str(path)


async def get_project_asset(
    session: AsyncSession,
    project_id: int,
    kind: str,
) -> ProjectAssetRecord | None:
    return await session.scalar(
        select(ProjectAssetRecord).where(
            ProjectAssetRecord.project_id == project_id,
            ProjectAssetRecord.kind == kind,
        )
    )


async def upsert_project_asset(
    session: AsyncSession,
    project_id: int,
    kind: str,
    payload: dict,
) -> ProjectAssetRecord:
    asset = await get_project_asset(session, project_id, kind)
    if asset is None:
        asset = ProjectAssetRecord(
            project_id=project_id,
            kind=kind,
            payload_json=payload,
        )
        session.add(asset)
    else:
        asset.payload_json = payload
    await session.commit()
    return asset
