from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mangadock_api.database import get_db
from mangadock_api.models import (
    LLMProviderRecord,
    ProjectProviderRouteRecord,
    ProjectRecord,
    ProviderCapabilityRecord,
)
from mangadock_api.schemas import (
    LLMProviderCreate,
    LLMProviderRead,
    LLMProviderUpdate,
)

router = APIRouter(prefix="/api/v1/llm-providers", tags=["llm-providers"])


async def get_provider(
    provider_id: int,
    session: AsyncSession,
    for_update: bool = False,
) -> LLMProviderRecord:
    provider = await session.get(
        LLMProviderRecord,
        provider_id,
        with_for_update=for_update,
    )
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found",
        )
    return provider


async def get_capabilities(
    session: AsyncSession,
    provider_id: int,
) -> list[str]:
    values = await session.scalars(
        select(ProviderCapabilityRecord.capability)
        .where(ProviderCapabilityRecord.provider_id == provider_id)
        .order_by(ProviderCapabilityRecord.id)
    )
    return list(values.all())


async def provider_read(
    provider: LLMProviderRecord,
    session: AsyncSession,
) -> LLMProviderRead:
    return LLMProviderRead(
        id=provider.id,
        name=provider.name,
        base_url=provider.base_url,
        model=provider.model,
        api_key_env=provider.api_key_env,
        enabled=provider.enabled,
        capabilities=await get_capabilities(session, provider.id),
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


async def referenced_roles(
    session: AsyncSession,
    provider_id: int,
) -> set[str]:
    roles = set(
        (
            await session.scalars(
                select(ProjectProviderRouteRecord.role).where(
                    ProjectProviderRouteRecord.provider_id == provider_id
                )
            )
        ).all()
    )
    project_id = await session.scalar(
        select(ProjectRecord.id)
        .where(ProjectRecord.provider_id == provider_id)
        .limit(1)
    )
    if project_id is not None:
        roles.add("script")
    return roles


def add_capabilities(
    session: AsyncSession,
    provider_id: int,
    capabilities: list[str],
) -> None:
    session.add_all(
        [
            ProviderCapabilityRecord(
                provider_id=provider_id,
                capability=capability,
            )
            for capability in capabilities
        ]
    )


@router.post("/", response_model=LLMProviderRead, status_code=201)
async def create_provider(
    payload: LLMProviderCreate,
    session: AsyncSession = Depends(get_db),
) -> LLMProviderRead:
    values = payload.model_dump(exclude={"capabilities"})
    values["base_url"] = str(payload.base_url)
    provider = LLMProviderRecord(**values)
    session.add(provider)
    try:
        await session.flush()
        add_capabilities(session, provider.id, payload.capabilities)
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provider name already exists",
        ) from error
    await session.refresh(provider)
    return await provider_read(provider, session)


@router.get("/", response_model=list[LLMProviderRead])
async def list_providers(
    session: AsyncSession = Depends(get_db),
) -> list[LLMProviderRead]:
    providers = list(
        (
            await session.scalars(
                select(LLMProviderRecord).order_by(LLMProviderRecord.id)
            )
        ).all()
    )
    return [await provider_read(provider, session) for provider in providers]


@router.get("/{provider_id}", response_model=LLMProviderRead)
async def read_provider(
    provider_id: int,
    session: AsyncSession = Depends(get_db),
) -> LLMProviderRead:
    provider = await get_provider(provider_id, session)
    return await provider_read(provider, session)


@router.patch("/{provider_id}", response_model=LLMProviderRead)
async def update_provider(
    provider_id: int,
    payload: LLMProviderUpdate,
    session: AsyncSession = Depends(get_db),
) -> LLMProviderRead:
    provider = await get_provider(provider_id, session, for_update=True)
    roles = await referenced_roles(session, provider_id)
    if payload.enabled is False and roles:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provider 已被项目使用，无法停用",
        )
    if "capabilities" in payload.model_fields_set:
        if payload.capabilities is None:
            raise HTTPException(status_code=422, detail="Capabilities 不能为空")
        missing_roles = roles - set(payload.capabilities)
        if missing_roles:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="无法移除项目正在使用的 Provider 能力",
            )

    values = payload.model_dump(exclude_unset=True, exclude={"capabilities"})
    if payload.base_url is not None:
        values["base_url"] = str(payload.base_url)
    for field, value in values.items():
        setattr(provider, field, value)
    if payload.capabilities is not None:
        await session.execute(
            delete(ProviderCapabilityRecord).where(
                ProviderCapabilityRecord.provider_id == provider_id
            )
        )
        add_capabilities(session, provider_id, payload.capabilities)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provider name already exists",
        ) from error
    await session.refresh(provider)
    return await provider_read(provider, session)


@router.delete("/{provider_id}", status_code=204)
async def delete_provider(
    provider_id: int,
    session: AsyncSession = Depends(get_db),
) -> Response:
    provider = await get_provider(provider_id, session, for_update=True)
    if await referenced_roles(session, provider_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provider 已被项目使用，无法删除",
        )
    await session.delete(provider)
    await session.commit()
    return Response(status_code=204)
