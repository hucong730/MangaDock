import json

import httpx
import pytest
import respx

from mangadock_providers.video_exceptions import (
    VideoProviderAPIError,
    VideoProviderConfigurationError,
    VideoProviderResponseError,
    VideoProviderTimeoutError,
    VideoProviderTransportError,
)
from mangadock_providers.wan import WanProvider

MP4 = b"fake-mp4"


def make_provider(client, tmp_path, **kwargs):
    return WanProvider(
        base_url="http://comfyui.test",
        output_dir=str(tmp_path),
        client=client,
        timeout_s=kwargs.pop("timeout_s", 1),
        poll_interval_s=kwargs.pop("poll_interval_s", 0),
        **kwargs,
    )


def history(media_kind="videos"):
    return {
        "prompt-1": {
            "status": {"status_str": "success"},
            "outputs": {
                "10": {
                    media_kind: [
                        {"filename": "clip.mp4", "subfolder": "", "type": "output"}
                    ]
                }
            },
        }
    }


def mock_success(mock, media_kind="videos"):
    mock.post("http://comfyui.test/upload/image").mock(
        return_value=httpx.Response(200, json={"name": "frame.png", "subfolder": ""})
    )
    prompt_route = mock.post("http://comfyui.test/prompt").mock(
        return_value=httpx.Response(200, json={"prompt_id": "prompt-1"})
    )
    history_route = mock.get("http://comfyui.test/history/prompt-1").mock(
        side_effect=[httpx.Response(200, json={}), httpx.Response(200, json=history(media_kind))]
    )
    mock.get("http://comfyui.test/view").mock(
        return_value=httpx.Response(200, content=MP4)
    )
    return history_route, prompt_route


@pytest.mark.asyncio
async def test_wan_generates_video_and_overrides_workflow(tmp_path) -> None:
    keyframe = tmp_path / "frame.png"
    keyframe.write_bytes(b"png")
    async with httpx.AsyncClient() as client:
        provider = make_provider(client, tmp_path)
        with respx.mock(assert_all_called=True) as mock:
            history_route, prompt_route = mock_success(mock)
            result = await provider.generate(
                str(keyframe), "测试运镜", 2, {"width": 320, "height": 240, "fps": 16}
            )
            payload = json.loads(prompt_route.calls[0].request.content)["prompt"]

    assert result.path.read_bytes() == MP4
    assert result.duration_s == 2
    assert result.source_duration_s == 2
    assert result.provider == "wan"
    assert len(history_route.calls) == 2
    assert payload["4"]["inputs"]["text"] == "测试运镜"
    assert payload["6"]["inputs"]["image"] == "frame.png"
    assert payload["7"]["inputs"]["length"] == 33


@pytest.mark.asyncio
async def test_wan_supports_gifs_and_backend_minimum(tmp_path) -> None:
    keyframe = tmp_path / "frame.png"
    keyframe.write_bytes(b"png")
    async with httpx.AsyncClient() as client:
        provider = make_provider(client, tmp_path)
        with respx.mock(assert_all_called=True) as mock:
            _, prompt_route = mock_success(mock, media_kind="gifs")
            result = await provider.generate(
                str(keyframe), "测试", 2, {"min_duration_s": 4, "fps": 16}
            )
            payload = json.loads(prompt_route.calls[0].request.content)["prompt"]

    assert result.duration_s == 2
    assert result.source_duration_s == 4
    assert payload["7"]["inputs"]["length"] == 65


@pytest.mark.asyncio
async def test_wan_rejects_invalid_duration_and_missing_template(tmp_path) -> None:
    provider = make_provider(httpx.AsyncClient(), tmp_path)
    with pytest.raises(VideoProviderConfigurationError):
        await provider.generate("frame.png", "test", 1, {})
    with pytest.raises(VideoProviderConfigurationError, match="template"):
        await provider.generate("frame.png", "test", 2, {"workflow_id": "missing"})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("route", "response", "exception_type"),
    [
        ("upload", httpx.ConnectError("offline"), VideoProviderTransportError),
        ("prompt", httpx.Response(500), VideoProviderAPIError),
        ("failed", httpx.Response(200, json={"prompt-1": {"status": {"status_str": "failed"}}}), VideoProviderResponseError),
        ("empty", httpx.Response(200, json={"prompt-1": {"status": {"status_str": "success"}, "outputs": {}}}), VideoProviderResponseError),
    ],
)
async def test_wan_maps_comfyui_errors(tmp_path, route, response, exception_type) -> None:
    keyframe = tmp_path / "frame.png"
    keyframe.write_bytes(b"png")
    async with httpx.AsyncClient() as client:
        provider = make_provider(client, tmp_path)
        with respx.mock(assert_all_called=False) as mock:
            if route == "upload":
                mock.post("http://comfyui.test/upload/image").mock(side_effect=response)
            else:
                mock.post("http://comfyui.test/upload/image").mock(
                    return_value=httpx.Response(200, json={"name": "frame.png"})
                )
                if route == "prompt":
                    mock.post("http://comfyui.test/prompt").mock(return_value=response)
                else:
                    mock.post("http://comfyui.test/prompt").mock(
                        return_value=httpx.Response(200, json={"prompt_id": "prompt-1"})
                    )
                    mock.get("http://comfyui.test/history/prompt-1").mock(
                        return_value=response
                    )
            with pytest.raises(exception_type):
                await provider.generate(str(keyframe), "test", 2, {})


@pytest.mark.asyncio
async def test_wan_timeout(tmp_path) -> None:
    keyframe = tmp_path / "frame.png"
    keyframe.write_bytes(b"png")
    async with httpx.AsyncClient() as client:
        provider = make_provider(client, tmp_path, timeout_s=0)
        with respx.mock(assert_all_called=True) as mock:
            mock.post("http://comfyui.test/upload/image").mock(
                return_value=httpx.Response(200, json={"name": "frame.png"})
            )
            mock.post("http://comfyui.test/prompt").mock(
                return_value=httpx.Response(200, json={"prompt_id": "prompt-1"})
            )
            mock.get("http://comfyui.test/history/prompt-1").mock(
                return_value=httpx.Response(200, json={})
            )
            with pytest.raises(VideoProviderTimeoutError):
                await provider.generate(str(keyframe), "test", 2, {})
