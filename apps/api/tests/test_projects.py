from unittest.mock import Mock

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from mangadock_api.models import ProjectEpisodeRecord, ProjectRecord, ProjectStageRecord
from mangadock_api.routers import projects


@pytest.fixture
def queue_mock(monkeypatch: pytest.MonkeyPatch) -> Mock:
    mock = Mock()
    monkeypatch.setattr(projects, "enqueue_task", mock)
    return mock


async def create_provider(client: AsyncClient, enabled: bool = True) -> int:
    response = await client.post(
        "/api/v1/llm-providers/",
        json={
            "name": f"provider-{enabled}",
            "base_url": "https://api.example.com/v1",
            "model": "fake",
            "api_key_env": "OPENAI_API_KEY",
            "enabled": enabled,
        },
    )
    return response.json()["id"]


async def upload_txt(
    client: AsyncClient,
    provider_id: int,
    content: bytes = "第一章 归来\n林夏回到旧港。".encode(),
):
    return await client.post(
        "/projects",
        data={"provider_id": str(provider_id)},
        files={"file": ("novel.txt", content, "text/plain")},
    )


@pytest.mark.asyncio
async def test_upload_list_status_and_assets(
    client: AsyncClient,
    session_factory,
    queue_mock: Mock,
) -> None:
    provider_id = await create_provider(client)

    created = await upload_txt(client, provider_id)

    assert created.status_code == 201
    project = created.json()
    assert project["title"] == "novel"
    assert project["novel_json"]["chapters"][0]["title"] == "第一章 归来"
    queue_mock.assert_called_once_with(
        "mangadock_worker.tasks.stage_outline",
        project["id"],
    )

    listed = await client.get("/projects")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["id"] == project["id"]

    detail = await client.get(f"/projects/{project['id']}")
    assert detail.status_code == 200
    assert detail.json()["novel_json"]["title"] == "novel"

    status = await client.get(f"/projects/{project['id']}/status")
    assert status.status_code == 200
    stages = {stage["stage"]: stage for stage in status.json()["stages"]}
    assert stages["upload"]["status"] == "done"
    assert stages["outline"]["status"] == "pending"
    assert stages["script"]["status"] == "pending"

    assert (await client.get(f"/projects/{project['id']}/outline")).status_code == 409
    assert (await client.get(f"/projects/{project['id']}/script")).status_code == 409

    async with session_factory() as session:
        record = await session.get(ProjectRecord, project["id"])
        record.outline_json = {"synopsis": "ready-outline"}
        record.script_json = {"episodes": ["ready-script"]}
        await session.commit()

    outline = await client.get(f"/projects/{project['id']}/outline")
    script = await client.get(f"/projects/{project['id']}/script")
    assert outline.json() == {"synopsis": "ready-outline"}
    assert script.json() == {"episodes": ["ready-script"]}


@pytest.mark.asyncio
async def test_provider_is_required_and_enabled(
    client: AsyncClient,
    queue_mock: Mock,
) -> None:
    missing = await upload_txt(client, 999)
    assert missing.status_code == 404

    disabled_id = await create_provider(client, enabled=False)
    disabled = await upload_txt(client, disabled_id)
    assert disabled.status_code == 409


@pytest.mark.asyncio
async def test_missing_project_routes_return_404(client: AsyncClient) -> None:
    for path in (
        "/projects/999",
        "/projects/999/status",
        "/projects/999/outline",
        "/projects/999/script",
    ):
        response = await client.get(path)
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_outline_retry_resets_downstream(
    client: AsyncClient,
    session_factory,
    queue_mock: Mock,
) -> None:
    provider_id = await create_provider(client)
    project = (await upload_txt(client, provider_id)).json()
    queue_mock.reset_mock()
    async with session_factory() as session:
        record = await session.get(ProjectRecord, project["id"])
        record.outline_json = {"old": True}
        record.script_json = {"old": True}
        outline_stage = await session.scalar(
            select(ProjectStageRecord).where(
                ProjectStageRecord.project_id == project["id"],
                ProjectStageRecord.stage == "outline",
            )
        )
        outline_stage.status = "failed"
        outline_stage.requires_attention = True
        session.add(
            ProjectEpisodeRecord(
                project_id=project["id"],
                episode=1,
                status="done",
                payload_json={"episode": 1},
            )
        )
        await session.commit()

    rejected = await client.post(f"/projects/{project['id']}/stages/video/retry")
    assert rejected.status_code == 422

    response = await client.post(f"/projects/{project['id']}/stages/outline/retry")

    assert response.status_code == 202
    queue_mock.assert_called_once_with(
        "mangadock_worker.tasks.stage_outline",
        project["id"],
    )
    async with session_factory() as session:
        record = await session.get(ProjectRecord, project["id"])
        episodes = list(
            (
                await session.scalars(
                    select(ProjectEpisodeRecord).where(
                        ProjectEpisodeRecord.project_id == project["id"]
                    )
                )
            ).all()
        )
    assert record.outline_json is None
    assert record.script_json is None
    assert episodes == []


@pytest.mark.asyncio
async def test_script_retry_requires_failed_stage_and_resets_episodes(
    client: AsyncClient,
    session_factory,
    queue_mock: Mock,
) -> None:
    provider_id = await create_provider(client)
    project = (await upload_txt(client, provider_id)).json()
    queue_mock.reset_mock()

    pending = await client.post(f"/projects/{project['id']}/stages/script/retry")
    assert pending.status_code == 409

    async with session_factory() as session:
        record = await session.get(ProjectRecord, project["id"])
        record.outline_json = {"ready": True}
        record.script_json = {"stale": True}
        script_stage = await session.scalar(
            select(ProjectStageRecord).where(
                ProjectStageRecord.project_id == project["id"],
                ProjectStageRecord.stage == "script",
            )
        )
        script_stage.status = "failed"
        session.add(
            ProjectEpisodeRecord(
                project_id=project["id"],
                episode=1,
                status="failed",
                attempt_count=1,
                error="bad",
                payload_json={"old": True},
            )
        )
        await session.commit()

    response = await client.post(f"/projects/{project['id']}/stages/script/retry")

    assert response.status_code == 202
    queue_mock.assert_called_once_with(
        "mangadock_worker.tasks.start_script",
        project["id"],
    )
    async with session_factory() as session:
        episode = await session.scalar(
            select(ProjectEpisodeRecord).where(
                ProjectEpisodeRecord.project_id == project["id"]
            )
        )
        record = await session.get(ProjectRecord, project["id"])
    assert episode.status == "pending"
    assert episode.attempt_count == 0
    assert episode.error is None
    assert episode.payload_json is None
    assert record.script_json is None
    assert (await client.get(f"/projects/{project['id']}/script")).status_code == 409


@pytest.mark.asyncio
async def test_enqueue_failure_keeps_retryable_project(
    client: AsyncClient,
    queue_mock: Mock,
) -> None:
    provider_id = await create_provider(client)
    queue_mock.side_effect = RuntimeError("broker down")

    created = await upload_txt(client, provider_id)

    assert created.status_code == 201
    project_id = created.json()["id"]
    status = await client.get(f"/projects/{project_id}/status")
    outline = next(
        stage for stage in status.json()["stages"] if stage["stage"] == "outline"
    )
    assert outline["status"] == "failed"
    assert outline["requires_attention"] is True
    assert "入队失败" in outline["error"]

    queue_mock.side_effect = None
    retry = await client.post(f"/projects/{project_id}/stages/outline/retry")
    assert retry.status_code == 202


@pytest.mark.asyncio
async def test_provider_used_by_project_cannot_be_deleted(
    client: AsyncClient,
    queue_mock: Mock,
) -> None:
    provider_id = await create_provider(client)
    project = (await upload_txt(client, provider_id)).json()

    response = await client.delete(f"/api/v1/llm-providers/{provider_id}")

    assert response.status_code == 409
    assert "项目使用" in response.json()["detail"]
    assert (await client.get(f"/api/v1/llm-providers/{provider_id}")).status_code == 200
    assert (await client.get(f"/projects/{project['id']}")).status_code == 200
