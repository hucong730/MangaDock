from io import BytesIO
from unittest.mock import Mock

import pytest
from httpx import AsyncClient
from pypdf import PdfWriter

from mangadock_api.routers import projects
from test_projects import create_provider, queue_mock, upload_txt


@pytest.mark.asyncio
async def test_rejects_unsupported_extension(
    client: AsyncClient,
    queue_mock: Mock,
) -> None:
    provider_id = await create_provider(client)

    response = await client.post(
        "/projects",
        data={"provider_id": str(provider_id)},
        files={"file": ("novel.epub", b"content", "application/epub+zip")},
    )

    assert response.status_code == 415


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "content", "message"),
    [
        ("empty.txt", b"", "空"),
        ("broken.pdf", b"not-a-pdf", "损坏"),
        ("invalid.txt", b"\xff\xfe\x00", "UTF-8"),
    ],
)
async def test_upload_errors_are_specific(
    client: AsyncClient,
    queue_mock: Mock,
    filename: str,
    content: bytes,
    message: str,
) -> None:
    provider_id = await create_provider(client)

    response = await client.post(
        "/projects",
        data={"provider_id": str(provider_id)},
        files={"file": (filename, content, "application/octet-stream")},
    )

    assert response.status_code == 422
    assert message in response.json()["detail"]


@pytest.mark.asyncio
async def test_encrypted_pdf_error(client: AsyncClient, queue_mock: Mock) -> None:
    provider_id = await create_provider(client)
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("secret")
    output = BytesIO()
    writer.write(output)

    response = await client.post(
        "/projects",
        data={"provider_id": str(provider_id)},
        files={"file": ("encrypted.pdf", output.getvalue(), "application/pdf")},
    )

    assert response.status_code == 422
    assert "加密" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_size_boundaries(
    client: AsyncClient,
    queue_mock: Mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_id = await create_provider(client)
    monkeypatch.setattr(projects.settings, "max_novel_chars", 30_000_000)

    accepted = await upload_txt(
        client,
        provider_id,
        b"a" * (20 * 1024 * 1024),
    )
    assert accepted.status_code == 201

    rejected = await upload_txt(
        client,
        provider_id,
        b"a" * (20 * 1024 * 1024 + 1),
    )
    assert rejected.status_code == 413


@pytest.mark.asyncio
async def test_novel_character_boundaries(
    client: AsyncClient,
    queue_mock: Mock,
) -> None:
    provider_id = await create_provider(client)

    accepted = await upload_txt(client, provider_id, "字".encode() * 120_000)
    assert accepted.status_code == 201

    rejected = await upload_txt(client, provider_id, "字".encode() * 120_001)
    assert rejected.status_code == 422
    assert "120000" in rejected.json()["detail"]


@pytest.mark.asyncio
async def test_empty_chapter_returns_422_not_500(
    client: AsyncClient,
    queue_mock: Mock,
) -> None:
    provider_id = await create_provider(client)

    response = await upload_txt(client, provider_id, "第一章\n第二章\n正文".encode())

    assert response.status_code == 422
    assert "正文" in response.json()["detail"]
