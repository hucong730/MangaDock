import json
from pathlib import Path

import httpx
import pytest
import respx

from mangadock_providers import (
    ComfyUIProvider,
    ImageProviderAPIError,
    ImageProviderConfigurationError,
    ImageProviderResponseError,
    ImageProviderTimeoutError,
    ImageProviderTransportError,
)

PNG = b"\x89PNG\r\n\x1a\nresult"


def make_provider(client: httpx.AsyncClient, tmp_path: Path, **overrides) -> ComfyUIProvider:
    return ComfyUIProvider(
        base_url="http://comfyui.test/",
        workflow_id="storyboard_keyframe_v1",
        output_dir=str(tmp_path),
        client=client,
        **overrides,
    )


@pytest.mark.asyncio
async def test_comfyui_uploads_references_submits_polls_and_downloads(tmp_path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    async with httpx.AsyncClient() as client:
        provider = make_provider(client, tmp_path)
        with respx.mock(assert_all_called=True) as mock:
            upload = mock.post("http://comfyui.test/upload/image").mock(
                side_effect=[
                    httpx.Response(200, json={"name": "first.png", "subfolder": ""}),
                    httpx.Response(200, json={"name": "second.png", "subfolder": ""}),
                ]
            )
            prompt = mock.post("http://comfyui.test/prompt").mock(
                return_value=httpx.Response(200, json={"prompt_id": "prompt-1"})
            )
            history = mock.get("http://comfyui.test/history/prompt-1").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "prompt-1": {
                            "status": {"status_str": "success"},
                            "outputs": {
                                "10": {
                                    "images": [
                                        {
                                            "filename": "frame.png",
                                            "subfolder": "",
                                            "type": "output",
                                        }
                                    ]
                                }
                            },
                        }
                    },
                )
            )
            view = mock.get("http://comfyui.test/view").mock(
                return_value=httpx.Response(200, content=PNG)
            )

            result = await provider.generate(
                "林夏，辫梢红绳；旧港仓库",
                [str(first), str(second)],
                (1024, 768),
            )

    assert result.path.read_bytes() == PNG
    assert result.width == 1024
    assert result.height == 768
    assert result.workflow_id == "storyboard_keyframe_v1"
    assert result.metadata["prompt_id"] == "prompt-1"
    assert len(upload.calls) == 2
    workflow = json.loads(prompt.calls.last.request.content)["prompt"]
    text_node = next(
        node for node in workflow.values()
        if node["class_type"] == "TextEncodeQwenImage21"
    )
    assert text_node["inputs"]["prompt"] == "林夏，辫梢红绳；旧港仓库"
    load_images = [
        node["inputs"]["image"]
        for node in workflow.values()
        if node["class_type"] == "LoadImage"
    ]
    assert load_images == ["first.png", "second.png"]
    assert history.called
    assert view.calls.last.request.url.params["filename"] == "frame.png"


@pytest.mark.asyncio
async def test_comfyui_rejects_more_than_four_references(tmp_path) -> None:
    files = []
    for index in range(5):
        path = tmp_path / f"{index}.png"
        path.write_bytes(b"x")
        files.append(str(path))

    with pytest.raises(ImageProviderConfigurationError):
        await make_provider(httpx.AsyncClient(), tmp_path).generate("test", files, (10, 10))


@pytest.mark.asyncio
async def test_comfyui_empty_output_is_response_error(tmp_path) -> None:
    async with httpx.AsyncClient() as client:
        provider = make_provider(client, tmp_path)
        with respx.mock(assert_all_called=True) as mock:
            mock.post("http://comfyui.test/prompt").mock(
                return_value=httpx.Response(200, json={"prompt_id": "prompt-1"})
            )
            mock.get("http://comfyui.test/history/prompt-1").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "prompt-1": {
                            "status": {"status_str": "success"},
                            "outputs": {},
                        }
                    },
                )
            )
            with pytest.raises(ImageProviderResponseError):
                await provider.generate("test", [], (10, 10))


@pytest.mark.asyncio
async def test_comfyui_http_error_is_api_error(tmp_path) -> None:
    async with httpx.AsyncClient() as client:
        provider = make_provider(client, tmp_path)
        with respx.mock(assert_all_called=True) as mock:
            mock.post("http://comfyui.test/prompt").mock(
                return_value=httpx.Response(500, json={"error": "failed"})
            )
            with pytest.raises(ImageProviderAPIError):
                await provider.generate("test", [], (10, 10))


@pytest.mark.asyncio
async def test_comfyui_timeout(tmp_path) -> None:
    async with httpx.AsyncClient() as client:
        provider = make_provider(client, tmp_path, timeout_s=0, poll_interval_s=0)
        with respx.mock(assert_all_called=True) as mock:
            mock.post("http://comfyui.test/prompt").mock(
                return_value=httpx.Response(200, json={"prompt_id": "prompt-1"})
            )
            mock.get("http://comfyui.test/history/prompt-1").mock(
                return_value=httpx.Response(
                    200,
                    json={"prompt-1": {"outputs": {"10": {"images": []}}}},
                )
            )
            with pytest.raises(ImageProviderTimeoutError):
                await provider.generate("test", [], (10, 10))


def successful_history() -> dict:
    return {
        "prompt-1": {
            "status": {"status_str": "success"},
            "outputs": {
                "10": {
                    "images": [
                        {"filename": "frame.png", "subfolder": "", "type": "output"}
                    ]
                }
            },
        }
    }


@pytest.mark.asyncio
async def test_comfyui_upload_transport_error(tmp_path) -> None:
    reference = tmp_path / "reference.png"
    reference.write_bytes(b"x")
    async with httpx.AsyncClient() as client:
        provider = make_provider(client, tmp_path)
        with respx.mock(assert_all_called=True) as mock:
            mock.post("http://comfyui.test/upload/image").mock(
                side_effect=httpx.ConnectError("offline")
            )
            with pytest.raises(ImageProviderTransportError):
                await provider.generate("test", [str(reference)], (10, 10))


@pytest.mark.asyncio
async def test_comfyui_upload_api_error_and_subfolder(tmp_path) -> None:
    reference = tmp_path / "reference.png"
    reference.write_bytes(b"x")
    async with httpx.AsyncClient() as client:
        provider = make_provider(client, tmp_path)
        with respx.mock(assert_all_called=True) as mock:
            mock.post("http://comfyui.test/upload/image").mock(
                return_value=httpx.Response(400, json={"error": "bad"})
            )
            with pytest.raises(ImageProviderAPIError):
                await provider.generate("test", [str(reference)], (10, 10))


@pytest.mark.asyncio
async def test_comfyui_prompt_response_and_transport_errors(tmp_path) -> None:
    async with httpx.AsyncClient() as client:
        provider = make_provider(client, tmp_path)
        with respx.mock(assert_all_called=True) as mock:
            mock.post("http://comfyui.test/prompt").mock(
                return_value=httpx.Response(200, json={})
            )
            with pytest.raises(ImageProviderResponseError):
                await provider.generate("test", [], (10, 10))

    async with httpx.AsyncClient() as client:
        provider = make_provider(client, tmp_path)
        with respx.mock(assert_all_called=True) as mock:
            mock.post("http://comfyui.test/prompt").mock(
                side_effect=httpx.ConnectError("offline")
            )
            with pytest.raises(ImageProviderTransportError):
                await provider.generate("test", [], (10, 10))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "exception_type"),
    [
        (httpx.Response(500, json={"error": "bad"}), ImageProviderAPIError),
        (httpx.Response(200, text="not-json"), ImageProviderResponseError),
        (httpx.Response(200, json={"prompt-1": []}), ImageProviderResponseError),
        (
            httpx.Response(
                200,
                json={"prompt-1": {"status": {"status_str": "failed"}}},
            ),
            ImageProviderResponseError,
        ),
    ],
)
async def test_comfyui_history_errors(
    tmp_path,
    response: httpx.Response,
    exception_type: type[Exception],
) -> None:
    async with httpx.AsyncClient() as client:
        provider = make_provider(client, tmp_path)
        with respx.mock(assert_all_called=True) as mock:
            mock.post("http://comfyui.test/prompt").mock(
                return_value=httpx.Response(200, json={"prompt_id": "prompt-1"})
            )
            mock.get("http://comfyui.test/history/prompt-1").mock(
                return_value=response
            )
            with pytest.raises(exception_type):
                await provider.generate("test", [], (10, 10))


@pytest.mark.asyncio
async def test_comfyui_history_transport_error(tmp_path) -> None:
    async with httpx.AsyncClient() as client:
        provider = make_provider(client, tmp_path)
        with respx.mock(assert_all_called=True) as mock:
            mock.post("http://comfyui.test/prompt").mock(
                return_value=httpx.Response(200, json={"prompt_id": "prompt-1"})
            )
            mock.get("http://comfyui.test/history/prompt-1").mock(
                side_effect=httpx.ConnectError("offline")
            )
            with pytest.raises(ImageProviderTransportError):
                await provider.generate("test", [], (10, 10))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "exception_type"),
    [
        (httpx.Response(500, content=b"bad"), ImageProviderAPIError),
        (httpx.ConnectError("offline"), ImageProviderTransportError),
    ],
)
async def test_comfyui_view_errors(
    tmp_path,
    response: httpx.Response | httpx.ConnectError,
    exception_type: type[Exception],
) -> None:
    async with httpx.AsyncClient() as client:
        provider = make_provider(client, tmp_path)
        with respx.mock(assert_all_called=True) as mock:
            mock.post("http://comfyui.test/prompt").mock(
                return_value=httpx.Response(200, json={"prompt_id": "prompt-1"})
            )
            mock.get("http://comfyui.test/history/prompt-1").mock(
                return_value=httpx.Response(200, json=successful_history())
            )
            view = mock.get("http://comfyui.test/view")
            if isinstance(response, httpx.ConnectError):
                view.mock(side_effect=response)
            else:
                view.mock(return_value=response)
            with pytest.raises(exception_type):
                await provider.generate("test", [], (10, 10))


@pytest.mark.asyncio
async def test_comfyui_polls_with_api_key_and_subfolder(tmp_path) -> None:
    reference = tmp_path / "reference.png"
    reference.write_bytes(b"x")
    async with httpx.AsyncClient() as client:
        provider = make_provider(
            client,
            tmp_path,
            api_key="secret",
            timeout_s=1,
            poll_interval_s=0,
        )
        with respx.mock(assert_all_called=True) as mock:
            mock.post("http://comfyui.test/upload/image").mock(
                return_value=httpx.Response(
                    200,
                    json={"name": "reference.png", "subfolder": "nested"},
                )
            )
            prompt = mock.post("http://comfyui.test/prompt").mock(
                return_value=httpx.Response(200, json={"prompt_id": "prompt-1"})
            )
            mock.get("http://comfyui.test/history/prompt-1").mock(
                side_effect=[
                    httpx.Response(
                        200,
                        json={"prompt-1": {"outputs": {"10": {"images": []}}}},
                    ),
                    httpx.Response(200, json=successful_history()),
                ]
            )
            mock.get("http://comfyui.test/view").mock(
                return_value=httpx.Response(200, content=PNG)
            )

            result = await provider.generate("test", [str(reference)], (10, 10))

    assert result.path.read_bytes() == PNG
    assert prompt.calls.last.request.headers["authorization"] == "Bearer secret"
    workflow = json.loads(prompt.calls.last.request.content)["prompt"]
    load_node = next(
        node for node in workflow.values() if node["class_type"] == "LoadImage"
    )
    assert load_node["inputs"]["image"] == "nested/reference.png"


@pytest.mark.asyncio
async def test_comfyui_empty_history_is_polled_until_success(tmp_path) -> None:
    async with httpx.AsyncClient() as client:
        provider = make_provider(client, tmp_path, timeout_s=1, poll_interval_s=0)
        with respx.mock(assert_all_called=True) as mock:
            mock.post("http://comfyui.test/prompt").mock(
                return_value=httpx.Response(200, json={"prompt_id": "prompt-1"})
            )
            history = mock.get("http://comfyui.test/history/prompt-1").mock(
                side_effect=[
                    httpx.Response(200, json={}),
                    httpx.Response(200, json=successful_history()),
                ]
            )
            mock.get("http://comfyui.test/view").mock(
                return_value=httpx.Response(200, content=PNG)
            )

            result = await provider.generate("test", [], (10, 10))

    assert result.path.read_bytes() == PNG
    assert len(history.calls) == 2


def test_templates_use_native_qwen_nodes_and_workflow_ids() -> None:
    root = Path("comfyui/templates")
    for name in ("character_anchor_v1", "character_views_v1", "storyboard_keyframe_v1"):
        workflow = json.loads((root / name).with_suffix(".json").read_text())
        assert any(
            node["class_type"] == "TextEncodeQwenImage21"
            for node in workflow.values()
        )
        assert any(node["class_type"] == "SaveImage" for node in workflow.values())
