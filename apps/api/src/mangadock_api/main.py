from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from mangadock_api.database import Base, engine, get_db
from mangadock_api import models
from mangadock_api.routers.providers import router as providers_router
from mangadock_api.routers.assets import router as assets_router
from mangadock_api.routers.characters import router as characters_router
from mangadock_api.routers.projects import router as projects_router
from mangadock_api.routers.storyboard import router as storyboard_router
from mangadock_api.routers.video_providers import router as video_providers_router


async def ensure_provider_capabilities(connection: AsyncConnection) -> None:
    await connection.execute(
        text(
            """
            INSERT INTO provider_capabilities (provider_id, capability)
            SELECT id, 'script' FROM llm_providers
            WHERE NOT EXISTS (
                SELECT 1 FROM provider_capabilities
                WHERE provider_capabilities.provider_id = llm_providers.id
            )
            """
        )
    )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await ensure_provider_capabilities(connection)
    yield


app = FastAPI(title="MangaDock API", lifespan=lifespan)
app.include_router(providers_router)
app.include_router(projects_router)
app.include_router(characters_router)
app.include_router(storyboard_router)
app.include_router(assets_router)
app.include_router(video_providers_router)


@app.get("/healthz")
async def health(session: AsyncSession = Depends(get_db)) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Database unavailable") from error
    return {"status": "ok", "database": "ok"}
