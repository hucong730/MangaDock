import json
import subprocess

import httpx
import pytest
import respx

from mangadock_providers.seedance import SeedanceProvider
from mangadock_providers.video_exceptions import (
    VideoProviderAPIError,
    VideoProviderConfigurationError,
    VideoProviderResponseError,
    VideoProviderTimeoutError,
    VideoProviderTransportError,
)

BASE = "https://ark.test/api/v3"


def mp4_bytes(tmp_path, duration_s=4):
    path = tmp_path / f"source-{duration_s}.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=24",
            "-t", str(duration_s), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path.read_bytes()


def make_provider(client, tmp_path, **kwargs):
    return SeedanceProvider(
        base_url=BASE,
        model="seedance-test",
        api_key="secret",
        output_dir=str(tmp_path),
        client=client,
        timeout_s=kwargs.pop("timeout_s", 1),
        poll_interval_s=0,
        **kwargs,
    )


def success_response():
    return httpx.Response(
        200,
        json={
            "id": "task-1",
            "status": "succeeded",
            "content": {"video_url": "https://cdn.test/video.mp4"},
        },
    )


@pytest.mark.asyncio
async def test_seedance_creates_polls_and_downloads_video(tmp_path) -> None:
    keyframe = tmp_path / "frame one.png"
    keyframe.write_bytes(b"png")
    async with httpx.AsyncClient() as client:
        provider = make_provider(client, tmp_path)
        with respx.mock(assert_all_called=True) as mock:
            create = mock.post(f"{BASE}/contents/generations/tasks").mock(
                return_value=httpx.Response(200, json={"id": "task-1"})
            )
            poll = mock.get(f"{BASE}/contents/generations/tasks/task-1").mock(
                side_effect=[httpx.Response(200, json={"status": "running"}), success_response()]
            )
            download = mock.get("https://cdn.test/video.mp4").mock(
                return_value=httpx.Response(200, content=mp4_bytes(tmp_path))
            )
            result = await provider.generate(str(keyframe), "测试", 2, {})

    assert result.duration_s == 2
    assert result.source_duration_s == 4
    assert result.provider == "seedance"
    assert len(poll.calls) == 2
    assert download.called
    assert "authorization" not in download.calls[0].request.headers
    payload = json.loads(create.calls[0].request.content)
    assert payload["duration"] == 4
    assert payload["generate_audio"] is False
    assert payload["content"][0]["text"] == "测试"
    assert payload["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert create.calls[0].request.headers["authorization"] == "Bearer secret"


@pytest.mark.asyncio
async def test_seedance_rejects_short_video(tmp_path) -> None:
    keyframe = tmp_path / "frame.png"
    keyframe.write_bytes(b"png")
    async with httpx.AsyncClient() as client:
        provider = make_provider(client, tmp_path)
        with respx.mock(assert_all_called=True) as mock:
            mock.post(f"{BASE}/contents/generations/tasks").mock(
                return_value=httpx.Response(200, json={"id": "task-1"})
            )
            mock.get(f"{BASE}/contents/generations/tasks/task-1").mock(
                return_value=success_response()
            )
            mock.get("https://cdn.test/video.mp4").mock(
                return_value=httpx.Response(200, content=mp4_bytes(tmp_path, duration_s=2))
            )
            with pytest.raises(VideoProviderResponseError, match="short"):
                await provider.generate(str(keyframe), "测试", 2, {})


@pytest.mark.asyncio
async def test_seedance_public_base_url_uses_each_keyframe_path(tmp_path) -> None:
    first = tmp_path / "one.png"
    second = tmp_path / "two.png"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    urls = []
    async with httpx.AsyncClient() as client:
        provider = make_provider(client, tmp_path)
        with respx.mock(assert_all_called=False) as mock:
            create = mock.post(f"{BASE}/contents/generations/tasks").mock(
                side_effect=lambda request: (
                    urls.append(json.loads(request.content)["content"][1]["image_url"]["url"]),
                    httpx.Response(500),
                )[1]
            )
            for path in (first, second):
                with pytest.raises(VideoProviderAPIError):
                    await provider.generate(
                        str(path), "测试", 2, {"public_asset_base_url": "https://assets.test/media"}
                    )

    assert urls == [
        "https://assets.test/media/one.png",
        "https://assets.test/media/two.png",
    ]


@pytest.mark.asyncio
async def test_seedance_rejects_missing_keyframe(tmp_path) -> None:
    provider = make_provider(httpx.AsyncClient(), tmp_path)
    with pytest.raises(VideoProviderConfigurationError, match="keyframe"):
        await provider.generate(str(tmp_path / "missing.png"), "test", 2, {})
    with pytest.raises(VideoProviderConfigurationError, match="duration"):
        await provider.generate("frame.png", "test", 1, {})


@pytest.mark.asyncio
async def test_seedance_rejects_missing_task_id(tmp_path) -> None:
    keyframe = tmp_path / "frame.png"
    keyframe.write_bytes(b"png")
    async with httpx.AsyncClient() as client:
        provider = make_provider(client, tmp_path)
        with respx.mock(assert_all_called=True) as mock:
            mock.post(f"{BASE}/contents/generations/tasks").mock(
                return_value=httpx.Response(200, json={})
            )
            with pytest.raises(VideoProviderResponseError, match="task id"):
                await provider.generate(str(keyframe), "test", 2, {})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("create_response", "poll_response", "exception_type"),
    [
        (httpx.Response(500), None, VideoProviderAPIError),
        (httpx.ConnectError("offline"), None, VideoProviderTransportError),
        (httpx.Response(200, text="not-json"), None, VideoProviderResponseError),
        (httpx.Response(200, json={"id": "task-1"}), httpx.Response(200, json={"status": "failed"}), VideoProviderResponseError),
        (httpx.Response(200, json={"id": "task-1"}), httpx.Response(200, json={"status": "succeeded", "content": {}}), VideoProviderResponseError),
    ],
)
async def test_seedance_maps_api_errors(tmp_path, create_response, poll_response, exception_type) -> None:
    keyframe = tmp_path / "frame.png"
    keyframe.write_bytes(b"png")
    async with httpx.AsyncClient() as client:
        provider = make_provider(client, tmp_path)
        with respx.mock(assert_all_called=False) as mock:
            create = mock.post(f"{BASE}/contents/generations/tasks")
            if isinstance(create_response, Exception):
                create.mock(side_effect=create_response)
            else:
                create.mock(return_value=create_response)
            if poll_response is not None:
                mock.get(f"{BASE}/contents/generations/tasks/task-1").mock(
                    return_value=poll_response
                )
            with pytest.raises(exception_type):
                await provider.generate(str(keyframe), "test", 2, {})


@pytest.mark.asyncio
async def test_seedance_timeout(tmp_path) -> None:
    keyframe = tmp_path / "frame.png"
    keyframe.write_bytes(b"png")
    async with httpx.AsyncClient() as client:
        provider = make_provider(client, tmp_path, timeout_s=0)
        with respx.mock(assert_all_called=True) as mock:
            mock.post(f"{BASE}/contents/generations/tasks").mock(
                return_value=httpx.Response(200, json={"id": "task-1"})
            )
            mock.get(f"{BASE}/contents/generations/tasks/task-1").mock(
                return_value=httpx.Response(200, json={"status": "queued"})
            )
            with pytest.raises(VideoProviderTimeoutError):
                await provider.generate(str(keyframe), "test", 2, {})
