import asyncio
import os
from contextvars import ContextVar

from celery import chord, group
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from mangadock_core.pipeline import build_script, generate_episode, generate_outline
from mangadock_core.schemas import Episode, Novel, Outline
from mangadock_persistence.database import SessionLocal
from mangadock_persistence.models import (
    LLMProviderRecord,
    ProjectEpisodeRecord,
    ProjectRecord,
    ProjectStageRecord,
)
from mangadock_providers import ProviderError
from mangadock_worker.celery_app import celery_app
from mangadock_worker.provider_factory import provider_for_record
from mangadock_worker.state import (
    increment_stage_progress,
    update_episode,
    update_stage,
)

session_factory_override = ContextVar("session_factory_override", default=None)


def new_session() -> AsyncSession:
    session_factory = session_factory_override.get() or SessionLocal
    return session_factory()


def run_async_task(coroutine):
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://mangadock:mangadock@postgres:5432/mangadock",
    )
    engine = (
        None
        if database_url.startswith("sqlite")
        else create_async_engine(database_url)
    )
    session_factory = (
        SessionLocal
        if engine is None
        else async_sessionmaker(engine, expire_on_commit=False)
    )

    async def run():
        token = session_factory_override.set(session_factory)
        try:
            return await coroutine
        finally:
            session_factory_override.reset(token)
            if engine is not None:
                await engine.dispose()

    return asyncio.run(run())


async def set_stage(project_id: int, stage_name: str, **values: object):
    async with new_session() as session:
        return await update_stage(session, project_id, stage_name, **values)


async def set_episode(project_id: int, episode_number: int, **values: object):
    async with new_session() as session:
        return await update_episode(session, project_id, episode_number, **values)


async def increment_progress(project_id: int, stage_name: str) -> None:
    async with new_session() as session:
        await increment_stage_progress(session, project_id, stage_name)


async def run_stage_outline(project_id: int) -> bool:
    await set_stage(
        project_id,
        "outline",
        status="running",
        completed_items=0,
        total_items=1,
        error=None,
        requires_attention=False,
    )
    async with new_session() as session:
        project = await session.get(ProjectRecord, project_id)
        provider_record = await session.get(LLMProviderRecord, project.provider_id)
        novel = Novel.model_validate(project.novel_json)

    try:
        provider = provider_for_record(provider_record)
    except ProviderError as error:
        await set_stage(
            project_id,
            "outline",
            status="failed",
            attempt_count=1,
            error=str(error),
            requires_attention=True,
        )
        return False

    last_error = None
    for attempt in range(1, 3):
        try:
            outline = await generate_outline(novel, provider)
        except (ProviderError, ValidationError, ValueError) as error:
            last_error = error
            await update_stage(
                new_session(),
                project_id,
                "outline",
                status="running",
                attempt_count=attempt,
                error=str(error),
            )
            continue

        async with new_session() as session:
            project = await session.get(ProjectRecord, project_id)
            project.outline_json = outline.model_dump(mode="json")
            await session.execute(
                delete(ProjectEpisodeRecord).where(
                    ProjectEpisodeRecord.project_id == project_id
                )
            )
            session.add_all(
                [
                    ProjectEpisodeRecord(
                        project_id=project_id,
                        episode=beat.episode,
                        status="pending",
                    )
                    for beat in outline.episode_beat
                ]
            )
            await update_stage(
                session,
                project_id,
                "outline",
                status="done",
                completed_items=1,
                attempt_count=attempt,
                error=None,
            )
            await update_stage(
                session,
                project_id,
                "script",
                status="pending",
                completed_items=0,
                total_items=len(outline.episode_beat),
                attempt_count=0,
                error=None,
                requires_attention=False,
            )
        try:
            start_script.delay(project_id)
        except Exception:
            await set_stage(
                project_id,
                "script",
                status="failed",
                error="任务入队失败，请重试",
                requires_attention=True,
            )
            return False
        return True

    await set_stage(
        project_id,
        "outline",
        status="failed",
        completed_items=0,
        attempt_count=2,
        error=str(last_error),
        requires_attention=True,
    )
    return False


@celery_app.task(name="mangadock_worker.tasks.stage_outline")
def stage_outline(project_id: int) -> bool:
    return run_async_task(run_stage_outline(project_id))


@celery_app.task(name="mangadock_worker.tasks.start_script")
def start_script(project_id: int) -> None:
    async def prepare() -> None:
        async with new_session() as session:
            episode_numbers = list(
                (
                    await session.scalars(
                        select(ProjectEpisodeRecord.episode)
                        .where(ProjectEpisodeRecord.project_id == project_id)
                        .order_by(ProjectEpisodeRecord.episode)
                    )
                ).all()
            )
            stage = await session.scalar(
                select(ProjectStageRecord).where(
                    ProjectStageRecord.project_id == project_id,
                    ProjectStageRecord.stage == "script",
                )
            )
            await update_stage(
                session,
                project_id,
                "script",
                status="running",
                completed_items=0,
                total_items=len(episode_numbers),
                attempt_count=stage.attempt_count + 1,
                error=None,
                requires_attention=False,
            )
        return episode_numbers

    episode_numbers = run_async_task(prepare())
    try:
        chord(
            group(
                [
                    stage_episode.s(project_id, episode_number)
                    for episode_number in episode_numbers
                ]
            ),
            stage_script.si(project_id),
        ).delay()
    except Exception:
        run_async_task(
            set_stage(
                project_id,
                "script",
                status="failed",
                error="任务入队失败，请重试",
                requires_attention=True,
            )
        )


async def run_stage_episode(project_id: int, episode_number: int) -> bool:
    async with new_session() as session:
        episode_record = await session.scalar(
            select(ProjectEpisodeRecord).where(
                ProjectEpisodeRecord.project_id == project_id,
                ProjectEpisodeRecord.episode == episode_number,
            )
        )
        attempt_count = episode_record.attempt_count + 1
    await set_episode(
        project_id,
        episode_number,
        status="running",
        attempt_count=attempt_count,
        error=None,
    )

    async with new_session() as session:
        project = await session.get(ProjectRecord, project_id)
        provider_record = await session.get(LLMProviderRecord, project.provider_id)
        outline = Outline.model_validate(project.outline_json)

    try:
        provider = provider_for_record(provider_record)
        episode = await generate_episode(outline, episode_number, provider)
    except (ProviderError, ValidationError, ValueError) as error:
        await set_episode(
            project_id,
            episode_number,
            status="failed",
            attempt_count=attempt_count,
            error=str(error),
        )
        await increment_progress(project_id, "script")
        return False

    await set_episode(
        project_id,
        episode_number,
        status="done",
        attempt_count=attempt_count,
        error=None,
        payload_json=episode.model_dump(mode="json"),
    )
    await increment_progress(project_id, "script")
    return True


@celery_app.task(name="mangadock_worker.tasks.stage_episode")
def stage_episode(project_id: int, episode_number: int) -> bool:
    return run_async_task(run_stage_episode(project_id, episode_number))


async def run_stage_script(project_id: int) -> bool:
    async with new_session() as session:
        records = list(
            (
                await session.scalars(
                    select(ProjectEpisodeRecord)
                    .where(ProjectEpisodeRecord.project_id == project_id)
                    .order_by(ProjectEpisodeRecord.episode)
                )
            ).all()
        )
        project = await session.get(ProjectRecord, project_id)

    if not records or any(record.status != "done" for record in records):
        await set_stage(
            project_id,
            "script",
            status="failed",
            error="One or more episodes failed",
            requires_attention=True,
        )
        return False

    try:
        outline = Outline.model_validate(project.outline_json)
        episodes = [Episode.model_validate(record.payload_json) for record in records]
        script = build_script(outline, episodes)
    except (ValidationError, ValueError) as error:
        await set_stage(
            project_id,
            "script",
            status="failed",
            error=str(error),
            requires_attention=True,
        )
        return False

    async with new_session() as session:
        project = await session.get(ProjectRecord, project_id)
        project.script_json = script.model_dump(mode="json")
        await update_stage(
            session,
            project_id,
            "script",
            status="done",
            completed_items=len(records),
            error=None,
            requires_attention=False,
        )
    from mangadock_worker.character_tasks import get_stage, stage_characters

    await get_stage(project_id, "characters")
    try:
        stage_characters.delay(project_id)
    except Exception:
        await set_stage(
            project_id,
            "characters",
            status="failed",
            error="任务入队失败，请重试",
            requires_attention=True,
        )
        return False
    return True


@celery_app.task(name="mangadock_worker.tasks.stage_script")
def stage_script(project_id: int) -> bool:
    return run_async_task(run_stage_script(project_id))
