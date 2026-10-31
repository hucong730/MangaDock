from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx

from mangadock_providers.remote_video import RemoteVideoClient, keyframe_url
from mangadock_providers.video_exceptions import (
    VideoProviderAPIError,
    VideoProviderConfigurationError,
    VideoProviderResponseError,
    VideoProviderTransportError,
)


def test_keyframe_url_handles_relative_paths_mime_and_size(tmp_path) -> None:
    assert keyframe_url("projects/1/a b.png", "https://cdn.test") == (
        "https://cdn.test/projects/1/a%20b.png"
    )
    image = tmp_path / "frame.webp"
    image.write_bytes(b"webp")
    assert keyframe_url(str(image)).startswith("data:image/webp;base64,")

    with patch.object(Path, "read_bytes", return_value=b"x" * (30 * 1024 * 1024 + 1)):
        with pytest.raises(VideoProviderConfigurationError, match="30MB"):
            keyframe_url(str(image))


@pytest.mark.asyncio
async def test_remote_client_rejects_non_object_json() -> None:
    async with httpx.AsyncClient() as client:
        remote = RemoteVideoClient(client, 1, 0)
        with respx.mock(assert_all_called=True) as mock:
            mock.get("https://video.test/task").mock(
                return_value=httpx.Response(200, json=[])
            )
            with pytest.raises(VideoProviderResponseError, match="non-object"):
                await remote.get_json("https://video.test/task", {})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "exception_type"),
    [
        (httpx.ConnectError("offline"), VideoProviderTransportError),
        (httpx.Response(500), VideoProviderAPIError),
    ],
)
async def test_remote_download_errors(tmp_path, response, exception_type) -> None:
    async with httpx.AsyncClient() as client:
        remote = RemoteVideoClient(client, 1, 0)
        with respx.mock(assert_all_called=True) as mock:
            route = mock.get("https://cdn.test/video.mp4")
            if isinstance(response, Exception):
                route.mock(side_effect=response)
            else:
                route.mock(return_value=response)
            with pytest.raises(exception_type):
                await remote.download("https://cdn.test/video.mp4", str(tmp_path), {})


@pytest.mark.asyncio
async def test_remote_download_maps_storage_error(tmp_path) -> None:
    async with httpx.AsyncClient() as client:
        remote = RemoteVideoClient(client, 1, 0)
        with respx.mock(assert_all_called=True) as mock:
            mock.get("https://cdn.test/video.mp4").mock(
                return_value=httpx.Response(200, content=b"mp4")
            )
            with patch.object(Path, "write_bytes", side_effect=OSError("disk full")):
                with pytest.raises(VideoProviderConfigurationError, match="store"):
                    await remote.download("https://cdn.test/video.mp4", str(tmp_path), {})
