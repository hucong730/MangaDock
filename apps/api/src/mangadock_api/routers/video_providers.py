from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mangadock_api.database import get_db
from mangadock_api.models import ProjectVideoRouteRecord, VideoProviderRecord
from mangadock_api.video_schemas import (
    VideoProviderCreate,
    VideoProviderRead,
    VideoProviderUpdate,
)

router = APIRouter(prefix="/api/v1/video-providers", tags=["video-providers"])


async def get_video_provider(
    session: AsyncSession,
    provider_id: int,
    for_update: bool = False,
) -> VideoProviderRecord:
    provider = await session.get(
        VideoProviderRecord, provider_id, with_for_update=for_update
    )
    if provider is None:
        raise HTTPException(status_code=404, detail="视频 Provider 不存在")
    return provider


async def is_referenced(session: AsyncSession, provider_id: int) -> bool:
    route_id = await session.scalar(
        select(ProjectVideoRouteRecord.id)
        .where(ProjectVideoRouteRecord.video_provider_id == provider_id)
        .limit(1)
    )
    return route_id is not None


@router.post("/", response_model=VideoProviderRead, status_code=201)
async def create_video_provider(
    payload: VideoProviderCreate,
    session: AsyncSession = Depends(get_db),
) -> VideoProviderRead:
    provider = VideoProviderRecord(**payload.model_dump())
    session.add(provider)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Provider 名称已存在") from error
    await session.refresh(provider)
    return VideoProviderRead.model_validate(provider)


@router.get("/", response_model=list[VideoProviderRead])
async def list_video_providers(
    session: AsyncSession = Depends(get_db),
) -> list[VideoProviderRead]:
    providers = list(
        (
            await session.scalars(
                select(VideoProviderRecord).order_by(VideoProviderRecord.id)
            )
        ).all()
    )
    return [VideoProviderRead.model_validate(provider) for provider in providers]


@router.get("/{provider_id}", response_model=VideoProviderRead)
async def read_video_provider(
    provider_id: int,
    session: AsyncSession = Depends(get_db),
) -> VideoProviderRead:
    provider = await get_video_provider(session, provider_id)
    return VideoProviderRead.model_validate(provider)


@router.patch("/{provider_id}", response_model=VideoProviderRead)
async def update_video_provider(
    provider_id: int,
    payload: VideoProviderUpdate,
    session: AsyncSession = Depends(get_db),
) -> VideoProviderRead:
    provider = await get_video_provider(session, provider_id, for_update=True)
    if payload.enabled is False and await is_referenced(session, provider_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provider 已被项目使用，无法停用",
        )
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(provider, field, value)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Provider 名称已存在") from error
    await session.refresh(provider)
    return VideoProviderRead.model_validate(provider)


@router.delete("/{provider_id}", status_code=204)
async def delete_video_provider(
    provider_id: int,
    session: AsyncSession = Depends(get_db),
) -> Response:
    provider = await get_video_provider(session, provider_id, for_update=True)
    if await is_referenced(session, provider_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provider 已被项目使用，无法删除",
        )
    await session.delete(provider)
    await session.commit()
    return Response(status_code=204)
