from unittest.mock import Mock

import pytest
from httpx import AsyncClient

from mangadock_api.models import CharacterImageRecord, CharacterRecord
from mangadock_api.routers import characters
from test_projects import create_provider


@pytest.mark.asyncio
async def test_character_list_anchor_confirmation_and_image_retry(
    client: AsyncClient,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_id = await create_provider(client)
    async with session_factory() as session:
        from mangadock_api.models import ProjectRecord

        project = ProjectRecord(
            title="旧港",
            source_filename="novel.txt",
            source_media_type="text/plain",
            provider_id=provider_id,
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
            status="done",
            path="assets/projects/1/front.png",
            width=1024,
            height=1024,
            format="png",
            workflow_id="character_anchor_v1",
        )
        session.add(image)
        await session.commit()
        project_id, character_id, image_id = project.id, character.id, image.id

    queue = Mock()
    monkeypatch.setattr(characters, "enqueue_task", queue)

    listed = await client.get(f"/api/v1/projects/{project_id}/characters")
    assert listed.status_code == 200
    assert listed.json()["characters"][0]["name"] == "林夏"

    confirmed = await client.post(
        f"/api/v1/projects/{project_id}/characters/{character_id}/anchor-confirmation"
    )
    assert confirmed.status_code == 202
    queue.assert_called_with("mangadock_worker.tasks.confirm_character_anchor", character_id)

    retried = await client.post(
        f"/api/v1/projects/{project_id}/character-images/{image_id}/regenerate"
    )
    assert retried.status_code == 202
    queue.assert_called_with("mangadock_worker.tasks.regenerate_character_image", image_id)
