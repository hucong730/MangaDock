import os

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from mangadock_persistence.database import Base
from mangadock_persistence.models import (
    CharacterImageRecord,
    CharacterRecord,
    LLMProviderRecord,
    ProjectAssetRecord,
    ProjectProviderRouteRecord,
    ProviderCapabilityRecord,
    ProjectEpisodeRecord,
    ProjectRecord,
    ProjectStageRecord,
)


@pytest.mark.asyncio
async def test_project_models_persist_json_and_stage_defaults() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as connection:
        provider = LLMProviderRecord(
            name="fake",
            base_url="https://api.example.com/v1",
            model="fake-model",
            api_key_env="OPENAI_API_KEY",
            enabled=True,
        )
        connection.add(provider)
        await connection.flush()
        project = ProjectRecord(
            title="旧港",
            source_filename="harbor.txt",
            source_media_type="text/plain",
            provider_id=provider.id,
            novel_json={
                "title": "旧港",
                "chapters": [{"index": 1, "title": "正文", "text": "内容"}],
            },
        )
        connection.add(project)
        await connection.flush()
        connection.add_all(
            [
                ProjectStageRecord(project_id=project.id, stage="outline"),
                ProjectStageRecord(
                    project_id=project.id,
                    stage="script",
                    total_items=2,
                ),
                ProjectEpisodeRecord(project_id=project.id, episode=1),
            ]
        )
        await connection.commit()
        await connection.refresh(project)

        assert project.id is not None
        assert project.novel_json["title"] == "旧港"
        assert project.outline_json is None
        assert project.script_json is None
        assert project.created_at is not None
        result = await connection.scalars(
            select(ProjectStageRecord).where(
                ProjectStageRecord.project_id == project.id
            )
        )
        stages = list(result.all())
        assert [stage.status for stage in stages] == ["pending", "pending"]
        assert stages[0].requires_attention is False
        assert stages[1].total_items == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_episode_number_is_unique_per_project() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as connection:
        provider = LLMProviderRecord(
            name="fake",
            base_url="https://api.example.com/v1",
            model="fake-model",
            api_key_env="OPENAI_API_KEY",
        )
        connection.add(provider)
        await connection.flush()
        project = ProjectRecord(
            title="旧港",
            source_filename="harbor.txt",
            source_media_type="text/plain",
            provider_id=provider.id,
            novel_json={"title": "旧港", "chapters": []},
        )
        connection.add(project)
        await connection.flush()
        connection.add(ProjectEpisodeRecord(project_id=project.id, episode=1))
        connection.add(ProjectEpisodeRecord(project_id=project.id, episode=1))
        with pytest.raises(IntegrityError):
            await connection.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_provider_capabilities_and_project_routes_are_unique() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        provider = LLMProviderRecord(
            name="fake",
            base_url="https://api.example.com/v1",
            model="fake-model",
            api_key_env="OPENAI_API_KEY",
        )
        session.add(provider)
        await session.flush()
        session.add_all(
            [
                ProviderCapabilityRecord(
                    provider_id=provider.id,
                    capability="script",
                ),
                ProviderCapabilityRecord(
                    provider_id=provider.id,
                    capability="script",
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

        project = ProjectRecord(
            title="旧港",
            source_filename="harbor.txt",
            source_media_type="text/plain",
            provider_id=provider.id,
            novel_json={"title": "旧港", "chapters": []},
        )
        session.add(project)
        await session.flush()
        session.add_all(
            [
                ProjectProviderRouteRecord(
                    project_id=project.id,
                    role="script",
                    provider_id=provider.id,
                ),
                ProjectProviderRouteRecord(
                    project_id=project.id,
                    role="script",
                    provider_id=provider.id,
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            await session.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_character_images_and_json_assets_track_state() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        provider = LLMProviderRecord(
            name="fake",
            base_url="https://api.example.com/v1",
            model="fake-model",
            api_key_env="OPENAI_API_KEY",
        )
        session.add(provider)
        await session.flush()
        project = ProjectRecord(
            title="旧港",
            source_filename="harbor.txt",
            source_media_type="text/plain",
            provider_id=provider.id,
            novel_json={"title": "旧港", "chapters": []},
        )
        session.add(project)
        await session.flush()
        character = CharacterRecord(
            project_id=project.id,
            name="林夏",
            biography="调查记者",
            prompt_zh="林夏，红绳学生装",
            prompt_en="Lin Xia, red ribbon uniform",
            voice_prompt="冷静女声",
            anchor_features=["红绳", "学生装", "短发", "眼睛", "录音笔"],
        )
        session.add(character)
        await session.flush()
        image = CharacterImageRecord(
            character_id=character.id,
            label="front_full",
            status="outdated",
            path="projects/1/images/front.png",
            width=1024,
            height=1024,
            format="png",
            workflow_id="character_anchor_v1",
        )
        session.add(image)
        session.add(
            ProjectAssetRecord(
                project_id=project.id,
                kind="characters",
                payload_json={"characters": []},
            )
        )
        await session.commit()

        assert character.anchor_confirmed is False
        assert image.status == "outdated"
        assert image.path == "projects/1/images/front.png"

        session.add(
            CharacterImageRecord(
                character_id=character.id,
                label="front_full",
                status="done",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
    await engine.dispose()
