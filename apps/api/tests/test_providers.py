import pytest
from httpx import AsyncClient, Response

from mangadock_api.models import ProjectProviderRouteRecord, ProjectRecord

ROUTE = "/api/v1/llm-providers/"
RESPONSE_FIELDS = {
    "id",
    "name",
    "base_url",
    "model",
    "api_key_env",
    "enabled",
    "capabilities",
    "created_at",
    "updated_at",
}


def payload(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "name": "primary",
        "base_url": "https://api.example.com/v1",
        "model": "example-model",
        "api_key_env": "TEST_PROVIDER_KEY",
        "enabled": True,
    }
    values.update(overrides)
    return values


@pytest.mark.asyncio
async def test_provider_crud_round_trip(client: AsyncClient) -> None:
    created = await client.post(ROUTE, json=payload())
    assert created.status_code == 201
    provider = created.json()
    assert set(provider) == RESPONSE_FIELDS
    assert provider["name"] == "primary"
    assert provider["base_url"] == "https://api.example.com/v1"
    assert provider["model"] == "example-model"
    assert provider["api_key_env"] == "TEST_PROVIDER_KEY"
    assert provider["enabled"] is True
    assert provider["capabilities"] == ["script"]
    assert isinstance(provider["id"], int)
    assert provider["created_at"]
    assert provider["updated_at"]

    listed = await client.get(ROUTE)
    assert listed.status_code == 200
    assert listed.json() == [provider]

    fetched = await client.get(f"{ROUTE}{provider['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == provider

    updated = await client.patch(
        f"{ROUTE}{provider['id']}",
        json={"model": "new-model", "enabled": False},
    )
    assert updated.status_code == 200
    assert updated.json()["model"] == "new-model"
    assert updated.json()["enabled"] is False
    assert updated.json()["name"] == "primary"

    deleted = await client.delete(f"{ROUTE}{provider['id']}")
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert (await client.get(f"{ROUTE}{provider['id']}")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", ""),
        ("name", "   "),
        ("model", ""),
        ("base_url", "not-a-url"),
        ("api_key_env", "lower-case"),
    ],
)
async def test_create_rejects_invalid_fields(
    client: AsyncClient,
    field: str,
    value: str,
) -> None:
    response = await client.post(ROUTE, json=payload(**{field: value}))
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_rejects_duplicate_name(client: AsyncClient) -> None:
    assert (await client.post(ROUTE, json=payload())).status_code == 201

    duplicate = await client.post(ROUTE, json=payload())

    assert duplicate.status_code == 409
    assert duplicate.json() == {"detail": "Provider name already exists"}


@pytest.mark.asyncio
async def test_update_rejects_duplicate_name(client: AsyncClient) -> None:
    first = (await client.post(ROUTE, json=payload())).json()
    second = (
        await client.post(ROUTE, json=payload(name="secondary"))
    ).json()

    response = await client.patch(
        f"{ROUTE}{second['id']}",
        json={"name": first["name"]},
    )

    assert response.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
async def test_missing_provider_returns_404(
    client: AsyncClient,
    method: str,
) -> None:
    response = await client.request(method, f"{ROUTE}999", json={})
    assert response.status_code == 404
    assert response.json() == {"detail": "Provider not found"}


@pytest.mark.asyncio
async def test_api_never_exposes_environment_secret(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "sentinel-secret-value"
    monkeypatch.setenv("TEST_PROVIDER_KEY", secret)

    responses: list[Response] = [await client.post(ROUTE, json=payload())]
    provider_id = responses[0].json()["id"]
    responses.extend(
        [
            await client.get(ROUTE),
            await client.get(f"{ROUTE}{provider_id}"),
            await client.patch(f"{ROUTE}{provider_id}", json={"model": "other"}),
        ]
    )

    for response in responses:
        assert response.status_code in {200, 201}
        assert secret not in response.text


@pytest.mark.asyncio
async def test_provider_capabilities_create_list_and_update(client: AsyncClient) -> None:
    created = await client.post(
        ROUTE,
        json=payload(capabilities=["script", "image", "video"]),
    )
    assert created.status_code == 201
    provider_id = created.json()["id"]
    assert created.json()["capabilities"] == ["script", "image", "video"]

    listed = await client.get(ROUTE)
    assert listed.json()[0]["capabilities"] == ["script", "image", "video"]

    updated = await client.patch(
        f"{ROUTE}{provider_id}",
        json={"capabilities": ["image"]},
    )
    assert updated.status_code == 200
    assert updated.json()["capabilities"] == ["image"]
    fetched = await client.get(f"{ROUTE}{provider_id}")
    assert fetched.json()["capabilities"] == ["image"]


@pytest.mark.asyncio
@pytest.mark.parametrize("capabilities", [[], ["unknown"], ["script", "script"]])
async def test_provider_rejects_invalid_capabilities(
    client: AsyncClient,
    capabilities: list[str],
) -> None:
    response = await client.post(ROUTE, json=payload(capabilities=capabilities))
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_route_referenced_provider_cannot_be_deleted_disabled_or_removed(
    client: AsyncClient,
    session_factory,
) -> None:
    created = await client.post(
        ROUTE,
        json=payload(capabilities=["script", "image"]),
    )
    provider_id = created.json()["id"]
    async with session_factory() as session:
        project = ProjectRecord(
            title="路由项目",
            source_filename="novel.txt",
            source_media_type="text/plain",
            provider_id=provider_id,
            novel_json={"title": "路由项目", "chapters": []},
        )
        session.add(project)
        await session.flush()
        session.add(
            ProjectProviderRouteRecord(
                project_id=project.id,
                role="image",
                provider_id=provider_id,
            )
        )
        await session.commit()

    deleted = await client.delete(f"{ROUTE}{provider_id}")
    assert deleted.status_code == 409

    disabled = await client.patch(f"{ROUTE}{provider_id}", json={"enabled": False})
    assert disabled.status_code == 409

    removed = await client.patch(
        f"{ROUTE}{provider_id}",
        json={"capabilities": ["script"]},
    )
    assert removed.status_code == 409

    allowed = await client.patch(
        f"{ROUTE}{provider_id}",
        json={"capabilities": ["script", "image"]},
    )
    assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_route_only_reference_is_protected_without_legacy_reference(
    client: AsyncClient,
    session_factory,
) -> None:
    legacy_id = (await client.post(ROUTE, json=payload(name="legacy"))).json()["id"]
    target_id = (
        await client.post(
            ROUTE,
            json=payload(name="image-only", capabilities=["script", "image"]),
        )
    ).json()["id"]
    async with session_factory() as session:
        project = ProjectRecord(
            title="仅路由引用",
            source_filename="novel.txt",
            source_media_type="text/plain",
            provider_id=legacy_id,
            novel_json={"title": "仅路由引用", "chapters": []},
        )
        session.add(project)
        await session.flush()
        session.add(
            ProjectProviderRouteRecord(
                project_id=project.id,
                role="image",
                provider_id=target_id,
            )
        )
        await session.commit()

    assert (await client.delete(f"{ROUTE}{target_id}")).status_code == 409
    assert (await client.patch(f"{ROUTE}{target_id}", json={"enabled": False})).status_code == 409
    assert (
        await client.patch(f"{ROUTE}{target_id}", json={"capabilities": ["script"]})
    ).status_code == 409
