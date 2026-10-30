from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mangadock_persistence.models import ProjectEpisodeRecord, ProjectStageRecord


async def update_stage(
    session: AsyncSession,
    project_id: int,
    stage_name: str,
    **values: object,
) -> ProjectStageRecord:
    stage = await session.scalar(
        select(ProjectStageRecord).where(
            ProjectStageRecord.project_id == project_id,
            ProjectStageRecord.stage == stage_name,
        )
    )
    if stage is None:
        raise ValueError(f"Missing {stage_name} stage for project {project_id}")
    for field, value in values.items():
        setattr(stage, field, value)
    await session.commit()
    await session.refresh(stage)
    return stage


async def update_episode(
    session: AsyncSession,
    project_id: int,
    episode_number: int,
    **values: object,
) -> ProjectEpisodeRecord:
    episode = await session.scalar(
        select(ProjectEpisodeRecord).where(
            ProjectEpisodeRecord.project_id == project_id,
            ProjectEpisodeRecord.episode == episode_number,
        )
    )
    if episode is None:
        raise ValueError(f"Missing episode {episode_number} for project {project_id}")
    for field, value in values.items():
        setattr(episode, field, value)
    await session.commit()
    await session.refresh(episode)
    return episode


async def increment_stage_progress(
    session: AsyncSession,
    project_id: int,
    stage_name: str,
) -> None:
    await session.execute(
        update(ProjectStageRecord)
        .where(
            ProjectStageRecord.project_id == project_id,
            ProjectStageRecord.stage == stage_name,
        )
        .values(completed_items=ProjectStageRecord.completed_items + 1)
    )
    await session.commit()
