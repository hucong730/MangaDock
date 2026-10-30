import os
from unittest.mock import Mock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["MANGADOCK_LLM_MODE"] = "fake"
os.environ["REDIS_URL"] = "redis://localhost:6379/9"

from mangadock_core.pipeline import build_script, generate_episode, generate_outline
from mangadock_core.schemas import Chapter, Novel
from mangadock_persistence.database import Base
from mangadock_persistence.models import (
    CharacterImageRecord,
    CharacterRecord,
    LLMProviderRecord,
    ProjectAssetRecord,
    ProjectProviderRouteRecord,
    ProjectRecord,
    ProjectStageRecord,
)
from mangadock_providers import FakeLLMProvider, ImageProviderAPIError, MockImageProvider
from mangadock_worker import character_tasks, pipeline_tasks
from mangadock_worker.character_tasks import (
    confirm_character_anchor,
    regenerate_character_image,
    run_character_stage,
)


class FlakyImageProvider(MockImageProvider):
    async def generate(self, prompt, reference_images, size):
        if "服装细节" in prompt:
            raise ImageProviderAPIError("detail failed")
        return await super().generate(prompt, reference_images, size)


@pytest_asyncio.fixture
async def project_factory(monkeypatch: pytest.MonkeyPatch, tmp_path):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(pipeline_tasks, "SessionLocal", session_factory)
    monkeypatch.setattr(character_tasks, "start_storyboard", Mock())
    monkeypatch.setattr(
        character_tasks,
        "image_provider_for_record",
        lambda record, workflow_id, output_dir: MockImageProvider(
            output_dir=output_dir,
            workflow_id=workflow_id,
        ),
    )

    async def create_project() -> int:
        llm = FakeLLMProvider()
        novel = Novel(
            title="旧港",
            chapters=[Chapter(index=1, title="正文", text="内容")],
        )
        outline = await generate_outline(novel, llm)
        episodes = [await generate_episode(outline, number, llm) for number in (1, 2)]
        script = build_script(outline, episodes)
        async with session_factory() as session:
            provider = LLMProviderRecord(
                name="fake",
                base_url="https://api.example.com/v1",
                model="fake",
                api_key_env="OPENAI_API_KEY",
            )
            session.add(provider)
            await session.flush()
            project = ProjectRecord(
                title="旧港",
                source_filename="novel.txt",
                source_media_type="text/plain",
                provider_id=provider.id,
                novel_json=novel.model_dump(mode="json"),
                outline_json=outline.model_dump(mode="json"),
                script_json=script.model_dump(mode="json"),
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
                        role="image",
                        provider_id=provider.id,
                    ),
                    ProjectStageRecord(project_id=project.id, stage="outline", status="done"),
                    ProjectStageRecord(project_id=project.id, stage="script", status="done"),
                ]
            )
            await session.commit()
            return project.id

    yield create_project, session_factory
    await engine.dispose()


async def characters(session_factory, project_id: int):
    async with session_factory() as session:
        result = await session.scalars(
            select(CharacterRecord).where(CharacterRecord.project_id == project_id)
        )
        return list(result.all())


async def images(session_factory, character_id: int):
    async with session_factory() as session:
        result = await session.scalars(
            select(CharacterImageRecord).where(
                CharacterImageRecord.character_id == character_id
            )
        )
        return list(result.all())


async def stage(session_factory, project_id: int, name: str):
    async with session_factory() as session:
        return await session.scalar(
            select(ProjectStageRecord).where(
                ProjectStageRecord.project_id == project_id,
                ProjectStageRecord.stage == name,
            )
        )


@pytest.mark.asyncio
async def test_anchor_generation_waits_for_confirmation(project_factory) -> None:
    create_project, session_factory = project_factory
    project_id = await create_project()

    assert await run_character_stage(project_id) is True

    character_list = await characters(session_factory, project_id)
    assert len(character_list) == 2
    assert all(not character.anchor_confirmed for character in character_list)
    for character in character_list:
        character_images = await images(session_factory, character.id)
        assert [image.label for image in character_images] == ["front_full"]
        assert character_images[0].status == "done"
        assert character_images[0].path.startswith(f"projects/{project_id}/images/")
        assert not character_images[0].path.startswith("/")
    assert (await stage(session_factory, project_id, "characters")).status == "waiting_confirmation"
    character_tasks.start_storyboard.delay.assert_not_called()


@pytest.mark.asyncio
async def test_confirmation_unlocks_views_and_storyboard(project_factory) -> None:
    create_project, session_factory = project_factory
    project_id = await create_project()
    assert await run_character_stage(project_id)
    character_list = await characters(session_factory, project_id)

    for character in character_list:
        assert await confirm_character_anchor(character.id) is True

    for character in character_list:
        character_images = await images(session_factory, character.id)
        assert {image.label for image in character_images} == {
            "front_full",
            "avatar",
            "profile",
            "back",
            "detail",
        }
        assert all(image.status == "done" for image in character_images)
    assert (await stage(session_factory, project_id, "characters")).status == "done"
    character_tasks.start_storyboard.delay.assert_called_once_with(project_id)


@pytest.mark.asyncio
async def test_failed_view_can_retry_without_affecting_other_images(project_factory) -> None:
    create_project, session_factory = project_factory
    project_id = await create_project()
    character_tasks.image_provider_for_record = (
        lambda record, workflow_id, output_dir: FlakyImageProvider(
            output_dir=output_dir,
            workflow_id=workflow_id,
        )
    )
    assert await run_character_stage(project_id)
    character_list = await characters(session_factory, project_id)
    for character in character_list:
        await confirm_character_anchor(character.id)

    assert (await stage(session_factory, project_id, "characters")).status == "failed"
    character_tasks.start_storyboard.delay.assert_not_called()
    failed = []
    for character in character_list:
        failed.extend(
            image for image in await images(session_factory, character.id)
            if image.status == "failed"
        )
    assert len(failed) == 2
    character_tasks.image_provider_for_record = (
        lambda record, workflow_id, output_dir: MockImageProvider(
            output_dir=output_dir,
            workflow_id=workflow_id,
        )
    )
    for image in failed:
        assert await regenerate_character_image(image.id) is True

    assert (await stage(session_factory, project_id, "characters")).status == "done"
    character_tasks.start_storyboard.delay.assert_called_once_with(project_id)


@pytest.mark.asyncio
async def test_storyboard_enqueue_failure_is_retryable(project_factory) -> None:
    create_project, session_factory = project_factory
    project_id = await create_project()
    assert await run_character_stage(project_id)
    character_list = await characters(session_factory, project_id)
    character_tasks.start_storyboard.delay.side_effect = RuntimeError("broker down")

    for character in character_list:
        result = await confirm_character_anchor(character.id)

    assert result is True
    assert (await stage(session_factory, project_id, "characters")).status == "done"
    storyboard = await stage(session_factory, project_id, "storyboard")
    assert storyboard.status == "failed"
    assert storyboard.requires_attention is True
    assert "入队失败" in storyboard.error


@pytest.mark.asyncio
async def test_regenerating_confirmed_anchor_invalidates_views(project_factory) -> None:
    create_project, session_factory = project_factory
    project_id = await create_project()
    assert await run_character_stage(project_id)
    character_list = await characters(session_factory, project_id)
    for character in character_list:
        await confirm_character_anchor(character.id)
    character_tasks.start_storyboard.delay.reset_mock()

    async with session_factory() as session:
        session.add(
            ProjectAssetRecord(
                project_id=project_id,
                kind="storyboard",
                payload_json={
                    "episodes": [
                        {
                            "episode": 1,
                            "segments": [
                                {
                                    "index": 1,
                                    "duration_s": 3,
                                    "cuts": [
                                        {
                                            "index": 1,
                                            "duration_s": 3,
                                            "characters": ["林夏"],
                                            "prompt": "林夏，红绳",
                                            "camera": "固定",
                                            "line_refs": [],
                                            "scene_ref": None,
                                            "keyframe_image": {
                                                "path": "old-frame.png",
                                                "width": 1024,
                                                "height": 1024,
                                                "format": "png",
                                                "workflow_id": "storyboard_keyframe_v1",
                                            },
                                        }
                                    ],
                                }
                            ],
                        }
                    ]
                },
            )
        )
        storyboard_stage = await session.scalar(
            select(ProjectStageRecord).where(
                ProjectStageRecord.project_id == project_id,
                ProjectStageRecord.stage == "storyboard",
            )
        )
        storyboard_stage.status = "done"
        await session.commit()

    anchor = (await images(session_factory, character_list[0].id))[0]
    assert await regenerate_character_image(anchor.id) is True

    async with session_factory() as session:
        character = await session.get(CharacterRecord, character_list[0].id)
        other_images = list(
            (
                await session.scalars(
                    select(CharacterImageRecord).where(
                        CharacterImageRecord.character_id == character_list[0].id,
                        CharacterImageRecord.label != "front_full",
                    )
                )
            ).all()
        )
    assert character.anchor_confirmed is False
    assert all(image.status == "outdated" for image in other_images)
    assert (await stage(session_factory, project_id, "characters")).status == "waiting_confirmation"
    storyboard = await session.scalar(
        select(ProjectAssetRecord).where(
            ProjectAssetRecord.project_id == project_id,
            ProjectAssetRecord.kind == "storyboard",
        )
    )
    cut = storyboard.payload_json["episodes"][0]["segments"][0]["cuts"][0]
    assert cut["keyframe_image"] is None
    assert (await stage(session_factory, project_id, "storyboard")).status == "pending"
    character_tasks.start_storyboard.delay.assert_not_called()
