import pytest
from httpx import AsyncClient

from mangadock_api.models import ProjectRecord, ProjectVideoRouteRecord
from test_projects import create_provider

ROUTE = "/api/v1/video-providers/"


def payload(**overrides):
    values = {
        "name": "wan-local",
        "kind": "wan",
        "base_url": "http://host.docker.internal:8188",
        "model": "wan2.2-ti2v-5b",
        "api_key_env": "COMFYUI_API_KEY",
        "enabled": True,
        "config_json": {"max_concurrency": 1, "min_duration_s": 2},
    }
    values.update(overrides)
    return values


@pytest.mark.asyncio
async def test_video_provider_crud_does_not_expose_secret(client: AsyncClient) -> None:
    created = await client.post(ROUTE, json=payload())

    assert created.status_code == 201
    provider = created.json()
    assert provider["kind"] == "wan"
    assert provider["config_json"]["max_concurrency"] == 1
    assert "secret" not in provider
    assert provider["api_key_env"] == "COMFYUI_API_KEY"

    listed = await client.get(ROUTE)
    assert listed.json() == [provider]
    updated = await client.patch(
        f"{ROUTE}{provider['id']}",
        json={"model": "wan-updated", "config_json": {"max_concurrency": 2}},
    )
    assert updated.status_code == 200
    assert updated.json()["model"] == "wan-updated"
    assert updated.json()["config_json"] == {"max_concurrency": 2}
    deleted = await client.delete(f"{ROUTE}{provider['id']}")
    assert deleted.status_code == 204
    assert (await client.get(f"{ROUTE}{provider['id']}")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "other"},
        {"config_json": {"max_concurrency": 0}},
        {"config_json": {"min_duration_s": 0}},
        {"config_json": {"public_asset_base_url": "ftp://assets.test"}},
    ],
)
async def test_video_provider_rejects_invalid_configuration(client: AsyncClient, overrides) -> None:
    response = await client.post(ROUTE, json=payload(**overrides))

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_referenced_video_provider_cannot_be_disabled_or_deleted(
    client: AsyncClient,
    session_factory,
) -> None:
    llm_provider_id = await create_provider(client)
    created = await client.post(ROUTE, json=payload())
    video_provider_id = created.json()["id"]
    async with session_factory() as session:
        project = ProjectRecord(
            title="旧港",
            source_filename="novel.txt",
            source_media_type="text/plain",
            provider_id=llm_provider_id,
            novel_json={"title": "旧港", "chapters": []},
        )
        session.add(project)
        await session.flush()
        session.add(
            ProjectVideoRouteRecord(
                project_id=project.id,
                episode=0,
                segment_index=0,
                video_provider_id=video_provider_id,
            )
        )
        await session.commit()
        project_id = project.id

    disabled = await client.patch(f"{ROUTE}{video_provider_id}", json={"enabled": False})
    deleted = await client.delete(f"{ROUTE}{video_provider_id}")

    assert disabled.status_code == 409
    assert deleted.status_code == 409
    assert project_id > 0
