from pathlib import Path

import pytest
from httpx import AsyncClient

from mangadock_api.models import ProjectAssetRecord, ProjectRecord
from test_projects import create_provider


@pytest.mark.asyncio
async def test_storyboard_and_asset_reading(
    client: AsyncClient,
    session_factory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_id = await create_provider(client)
    async with session_factory() as session:
        project = ProjectRecord(
            title="旧港",
            source_filename="novel.txt",
            source_media_type="text/plain",
            provider_id=provider_id,
            novel_json={"title": "旧港", "chapters": []},
        )
        session.add(project)
        await session.flush()
        session.add(
            ProjectAssetRecord(
                project_id=project.id,
                kind="storyboard",
                payload_json={"episodes": [{"episode": 1, "segments": []}]},
            )
        )
        await session.commit()
        project_id = project.id
    asset_root = tmp_path / "assets"
    image = asset_root / "projects" / str(project_id) / "frame.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"png")
    monkeypatch.setenv("ASSET_ROOT", str(asset_root))

    board = await client.get(f"/api/v1/projects/{project_id}/storyboard")
    assert board.status_code == 200
    assert board.json()["episodes"][0]["episode"] == 1

    relative = image.relative_to(asset_root)
    response = await client.get(f"/api/v1/assets/{relative}")
    assert response.status_code == 200
    assert response.content == b"png"

    traversal = await client.get("/api/v1/assets/..%2Fsecret.txt")
    assert traversal.status_code == 404


@pytest.mark.asyncio
async def test_storyboard_missing_returns_409(client: AsyncClient) -> None:
    response = await client.get("/api/v1/projects/999/storyboard")
    assert response.status_code == 404
