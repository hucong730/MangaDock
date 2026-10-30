from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mangadock_api.database import get_db
from mangadock_api.models import LLMProviderRecord
from mangadock_api.schemas import (
    LLMProviderCreate,
    LLMProviderRead,
    LLMProviderUpdate,
)

router = APIRouter(prefix="/api/v1/llm-providers", tags=["llm-providers"])


async def get_provider(
    provider_id: int,
    session: AsyncSession,
) -> LLMProviderRecord:
    provider = await session.get(LLMProviderRecord, provider_id)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found",
        )
    return provider


@router.post("/", response_model=LLMProviderRead, status_code=201)
async def create_provider(
    payload: LLMProviderCreate,
    session: AsyncSession = Depends(get_db),
) -> LLMProviderRecord:
    values = payload.model_dump()
    values["base_url"] = str(payload.base_url)
    provider = LLMProviderRecord(**values)
    session.add(provider)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provider name already exists",
        ) from error
    await session.refresh(provider)
    return provider


@router.get("/", response_model=list[LLMProviderRead])
async def list_providers(
    session: AsyncSession = Depends(get_db),
) -> list[LLMProviderRecord]:
    result = await session.scalars(
        select(LLMProviderRecord).order_by(LLMProviderRecord.id)
    )
    return list(result.all())


@router.get("/{provider_id}", response_model=LLMProviderRead)
async def read_provider(
    provider_id: int,
    session: AsyncSession = Depends(get_db),
) -> LLMProviderRecord:
    return await get_provider(provider_id, session)


@router.patch("/{provider_id}", response_model=LLMProviderRead)
async def update_provider(
    provider_id: int,
    payload: LLMProviderUpdate,
    session: AsyncSession = Depends(get_db),
) -> LLMProviderRecord:
    provider = await get_provider(provider_id, session)
    values = payload.model_dump(exclude_unset=True)
    if payload.base_url is not None:
        values["base_url"] = str(payload.base_url)
    for field, value in values.items():
        setattr(provider, field, value)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provider name already exists",
        ) from error
    await session.refresh(provider)
    return provider


@router.delete("/{provider_id}", status_code=204)
async def delete_provider(
    provider_id: int,
    session: AsyncSession = Depends(get_db),
) -> Response:
    provider = await get_provider(provider_id, session)
    await session.delete(provider)
    await session.commit()
    return Response(status_code=204)
