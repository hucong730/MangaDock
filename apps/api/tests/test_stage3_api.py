from unittest.mock import Mock

import pytest
from httpx import AsyncClient

from mangadock_api.models import (
    CharacterImageRecord,
    CharacterRecord,
    ProjectRecord,
    ProjectStageRecord,
)
from mangadock_api.routers import characters, projects
from test_projects import create_provider


async def create_character(session_factory, provider_id: int, project_suffix: str = "a"):
    async with session_factory() as session:
        project = ProjectRecord(
            title=f"项目{project_suffix}",
            source_filename="novel.txt",
            source_media_type="text/plain",
            provider_id=provider_id,
            novel_json={"title": "项目", "chapters": []},
        )
        session.add(project)
        await session.flush()
        character = CharacterRecord(
            project_id=project.id,
            name="林夏",
            biography="调查记者",
            prompt_zh="林夏",
            prompt_en="Lin Xia",
            voice_prompt="冷静女声",
            anchor_features=["红绳", "学生装", "短发", "眼睛", "录音笔"],
        )
        session.add(character)
        await session.flush()
        session.add_all(
            [
                CharacterImageRecord(
                    character_id=character.id,
                    label="front_full",
                    status="pending",
                    path=None,
                ),
                CharacterImageRecord(
                    character_id=character.id,
                    label="avatar",
                    status="pending",
                    path=None,
                ),
                ProjectStageRecord(
                    project_id=project.id,
                    stage="characters",
                    status="failed",
                ),
                ProjectStageRecord(
                    project_id=project.id,
                    stage="storyboard",
                    status="failed",
                ),
            ]
        )
        await session.commit()
        return project, character


@pytest.mark.asyncio
async def test_invalid_anchor_actions_return_409(
    client: AsyncClient,
    session_factory,
) -> None:
    provider_id = await create_provider(client)
    project, character = await create_character(session_factory, provider_id)

    confirm = await client.post(
        f"/api/v1/projects/{project.id}/characters/{character.id}/anchor-confirmation"
    )
    assert confirm.status_code == 409

    image = (
        await client.get(f"/api/v1/projects/{project.id}/characters")
    ).json()["characters"][0]["images"][1]
    regenerate = await client.post(
        f"/api/v1/projects/{project.id}/character-images/{image['id']}/regenerate"
    )
    assert regenerate.status_code == 409


@pytest.mark.asyncio
async def test_image_regeneration_checks_project_ownership(
    client: AsyncClient,
    session_factory,
) -> None:
    provider_id = await create_provider(client)
    first, _ = await create_character(session_factory, provider_id, "a")
    second, _ = await create_character(session_factory, provider_id, "b")
    image = (
        await client.get(f"/api/v1/projects/{second.id}/characters")
    ).json()["characters"][0]["images"][0]

    response = await client.post(
        f"/api/v1/projects/{first.id}/character-images/{image['id']}/regenerate"
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_character_and_storyboard_stages_can_retry(
    client: AsyncClient,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_id = await create_provider(client)
    project, _ = await create_character(session_factory, provider_id)
    queue = Mock()
    monkeypatch.setattr(projects, "enqueue_task", queue)

    characters_retry = await client.post(
        f"/api/v1/projects/{project.id}/stages/characters/retry"
    )
    storyboard_retry = await client.post(
        f"/api/v1/projects/{project.id}/stages/storyboard/retry"
    )

    assert characters_retry.status_code == 202
    assert storyboard_retry.status_code == 202
    assert queue.call_args_list[0].args == (
        "mangadock_worker.tasks.stage_characters",
        project.id,
    )
    assert queue.call_args_list[1].args == (
        "mangadock_worker.tasks.stage_storyboard",
        project.id,
    )
