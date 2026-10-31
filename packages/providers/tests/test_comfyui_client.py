import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx

from mangadock_providers.video_exceptions import (
    VideoProviderConfigurationError,
    VideoProviderResponseError,
)
from mangadock_providers.wan import WanProvider


def test_wan_template_uses_native_wan_nodes_and_models() -> None:
    template = json.loads(
        Path("comfyui/templates/wan_i2v_v1.json").read_text(encoding="utf-8")
    )

    assert template["1"]["class_type"] == "UNETLoader"
    assert template["1"]["inputs"]["unet_name"] == "wan2.2_ti2v_5B_fp16.safetensors"
    assert template["2"]["inputs"]["clip_name"] == "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
    assert template["3"]["inputs"]["vae_name"] == "wan2.2_vae.safetensors"
    assert template["7"]["class_type"] == "Wan22ImageToVideoLatent"
    assert template["10"]["class_type"] == "SaveVideo"


@pytest.mark.asyncio
async def test_comfyui_client_rejects_missing_keyframe(tmp_path) -> None:
    provider = WanProvider("http://comfyui.test", str(tmp_path))

    with pytest.raises(VideoProviderConfigurationError, match="keyframe"):
        await provider.generate(str(tmp_path / "missing.png"), "test", 2, {})


@pytest.mark.asyncio
async def test_comfyui_client_rejects_invalid_upload_json(tmp_path) -> None:
    keyframe = tmp_path / "frame.png"
    keyframe.write_bytes(b"png")
    async with httpx.AsyncClient() as client:
        provider = WanProvider(
            "http://comfyui.test", str(tmp_path), client=client, poll_interval_s=0
        )
        with respx.mock(assert_all_called=True) as mock:
            mock.post("http://comfyui.test/upload/image").mock(
                return_value=httpx.Response(200, text="not-json")
            )
            with pytest.raises(VideoProviderResponseError, match="upload response"):
                await provider.generate(str(keyframe), "test", 2, {})


@pytest.mark.asyncio
async def test_comfyui_client_maps_storage_errors(tmp_path) -> None:
    keyframe = tmp_path / "frame.png"
    keyframe.write_bytes(b"png")
    async with httpx.AsyncClient() as client:
        provider = WanProvider(
            "http://comfyui.test", str(tmp_path), client=client, poll_interval_s=0
        )
        with respx.mock(assert_all_called=True) as mock:
            mock.post("http://comfyui.test/upload/image").mock(
                return_value=httpx.Response(200, json={"name": "frame.png"})
            )
            mock.post("http://comfyui.test/prompt").mock(
                return_value=httpx.Response(200, json={"prompt_id": "prompt-1"})
            )
            mock.get("http://comfyui.test/history/prompt-1").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "prompt-1": {
                            "status": {"status_str": "success"},
                            "outputs": {
                                "10": {
                                    "videos": [
                                        {"filename": "clip.mp4", "type": "output"}
                                    ]
                                }
                            },
                        }
                    },
                )
            )
            mock.get("http://comfyui.test/view").mock(
                return_value=httpx.Response(200, content=b"mp4")
            )
            with patch.object(Path, "write_bytes", side_effect=OSError("disk full")):
                with pytest.raises(VideoProviderConfigurationError, match="store"):
                    await provider.generate(str(keyframe), "test", 2, {})
