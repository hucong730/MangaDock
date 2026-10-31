import uuid
from collections.abc import Mapping
from typing import Any, Optional

import httpx

from mangadock_providers.comfyui_client import ComfyUIClientError, ComfyUIHttpClient
from mangadock_providers.video_base import VideoProvider, VideoResult
from mangadock_providers.video_exceptions import (
    VideoProviderAPIError,
    VideoProviderConfigurationError,
    VideoProviderResponseError,
    VideoProviderTimeoutError,
    VideoProviderTransportError,
)

ERROR_TYPES = {
    "configuration": VideoProviderConfigurationError,
    "transport": VideoProviderTransportError,
    "api": VideoProviderAPIError,
    "response": VideoProviderResponseError,
    "timeout": VideoProviderTimeoutError,
}


class WanProvider(VideoProvider):
    def __init__(
        self,
        base_url: str,
        output_dir: str,
        api_key: str = "",
        workflow_id: str = "wan_i2v_v1",
        client: Optional[httpx.AsyncClient] = None,
        timeout_s: float = 300,
        poll_interval_s: float = 2,
    ) -> None:
        self._client = ComfyUIHttpClient(
            base_url=base_url,
            api_key=api_key,
            client=client,
            timeout_s=timeout_s,
            poll_interval_s=poll_interval_s,
        )
        self._workflow_id = workflow_id
        self._output_dir = output_dir

    async def generate(
        self,
        keyframe_image: str,
        prompt: str,
        duration_s: int,
        config: Mapping[str, Any],
    ) -> VideoResult:
        if duration_s < 2 or duration_s > 5:
            raise VideoProviderConfigurationError("Wan duration must be 2-5 seconds")
        try:
            source_duration = max(duration_s, int(config.get("min_duration_s", 2)))
            width = int(config.get("width", 320))
            height = int(config.get("height", 240))
            fps = int(config.get("fps", 16))
            workflow = self._client.load_template(
                str(config.get("workflow_id", self._workflow_id))
            )
            workflow["4"]["inputs"]["text"] = prompt
            workflow["6"]["inputs"]["image"] = await self._client.upload_image(
                keyframe_image
            )
            workflow["7"]["inputs"].update(
                {
                    "width": width,
                    "height": height,
                    "length": source_duration * fps + 1,
                }
            )
            workflow["8"]["inputs"]["seed"] = uuid.uuid4().int % (2**31)
            workflow["10"]["inputs"]["fps"] = fps
            prompt_id = await self._client.submit(workflow)
            metadata = await self._client.poll_media(
                prompt_id, ("videos", "gifs")
            )
            path = await self._client.download(metadata, self._output_dir, ".mp4")
        except ComfyUIClientError as error:
            raise ERROR_TYPES[error.kind](str(error)) from error
        return VideoResult(
            path=path,
            duration_s=duration_s,
            source_duration_s=source_duration,
            width=width,
            height=height,
            format="mp4",
            provider="wan",
            metadata={"prompt_id": prompt_id, **metadata},
        )
