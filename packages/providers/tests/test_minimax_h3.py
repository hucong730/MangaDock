import json

import httpx
import pytest
import respx

from mangadock_providers.minimax_h3 import MinimaxH3Provider
from mangadock_providers.video_exceptions import (
    VideoProviderConfigurationError,
    VideoProviderResponseError,
    VideoProviderTimeoutError,
)

BASE = "https://minimax.test"


def success_response():
    return httpx.Response(
        200,
        json={
            "task": {
                "id": "task-1",
                "status": "succeeded",
                "content": {"url": "https://cdn.test/h3.mp4"},
            }
        },
    )


@pytest.mark.asyncio
async def test_minimax_h3_uses_first_frame_and_minimum_duration(tmp_path) -> None:
    keyframe = tmp_path / "frame.png"
    keyframe.write_bytes(b"png")
    async with httpx.AsyncClient() as client:
        provider = MinimaxH3Provider(
            BASE, "MiniMax-H3", "secret", str(tmp_path), client=client, poll_interval_s=0
        )
        with respx.mock(assert_all_called=True) as mock:
            create = mock.post(f"{BASE}/v2/video_generation").mock(
                return_value=httpx.Response(200, json={"task_id": "task-1"})
            )
            mock.get(f"{BASE}/v2/video_generation/task-1").mock(
                side_effect=[httpx.Response(200, json={"task": {"status": "running"}}), success_response()]
            )
            mock.get("https://cdn.test/h3.mp4").mock(
                return_value=httpx.Response(200, content=b"mp4")
            )
            result = await provider.generate(str(keyframe), "三字段提示词", 2, {})

    assert result.duration_s == 2
    assert result.source_duration_s == 4
    assert result.provider == "minimax_h3"
    payload = json.loads(create.calls[0].request.content)
    assert payload["duration"] == 4
    assert payload["content"][0] == {"type": "text", "text": "三字段提示词"}
    assert payload["content"][1]["role"] == "first_frame"
    assert payload["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_minimax_h3_rejects_invalid_duration_and_missing_task_id(tmp_path) -> None:
    provider = MinimaxH3Provider(BASE, "MiniMax-H3", "secret", str(tmp_path))
    with pytest.raises(VideoProviderConfigurationError, match="duration"):
        await provider.generate("frame.png", "test", 1, {})

    keyframe = tmp_path / "frame.png"
    keyframe.write_bytes(b"png")
    async with httpx.AsyncClient() as client:
        provider = MinimaxH3Provider(
            BASE, "MiniMax-H3", "secret", str(tmp_path), client=client
        )
        with respx.mock(assert_all_called=True) as mock:
            mock.post(f"{BASE}/v2/video_generation").mock(
                return_value=httpx.Response(200, json={})
            )
            with pytest.raises(VideoProviderResponseError, match="task id"):
                await provider.generate(str(keyframe), "test", 2, {})


@pytest.mark.asyncio
async def test_minimax_h3_rejects_failed_and_malformed_tasks(tmp_path) -> None:
    keyframe = tmp_path / "frame.png"
    keyframe.write_bytes(b"png")
    async with httpx.AsyncClient() as client:
        provider = MinimaxH3Provider(
            BASE, "MiniMax-H3", "secret", str(tmp_path), client=client, poll_interval_s=0
        )
        with respx.mock(assert_all_called=False) as mock:
            mock.post(f"{BASE}/v2/video_generation").mock(
                return_value=httpx.Response(200, json={"task_id": "task-1"})
            )
            poll = mock.get(f"{BASE}/v2/video_generation/task-1")
            poll.mock(return_value=httpx.Response(200, json={"task": {"status": "failed"}}))
            with pytest.raises(VideoProviderResponseError):
                await provider.generate(str(keyframe), "test", 2, {})
            poll.mock(return_value=httpx.Response(200, json={"task": {"status": "succeeded", "content": {}}}))
            with pytest.raises(VideoProviderResponseError):
                await provider.generate(str(keyframe), "test", 2, {})


@pytest.mark.asyncio
async def test_minimax_h3_timeout(tmp_path) -> None:
    keyframe = tmp_path / "frame.png"
    keyframe.write_bytes(b"png")
    async with httpx.AsyncClient() as client:
        provider = MinimaxH3Provider(
            BASE, "MiniMax-H3", "secret", str(tmp_path), client=client,
            timeout_s=0, poll_interval_s=0,
        )
        with respx.mock(assert_all_called=True) as mock:
            mock.post(f"{BASE}/v2/video_generation").mock(
                return_value=httpx.Response(200, json={"task_id": "task-1"})
            )
            mock.get(f"{BASE}/v2/video_generation/task-1").mock(
                return_value=httpx.Response(200, json={"task": {"status": "queued"}})
            )
            with pytest.raises(VideoProviderTimeoutError):
                await provider.generate(str(keyframe), "test", 2, {})
