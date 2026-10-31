from collections.abc import Mapping
from typing import Any, Optional

import httpx

from mangadock_providers.remote_video import RemoteVideoClient, keyframe_url, video_result
from mangadock_providers.video_base import VideoProvider, VideoResult
from mangadock_providers.video_exceptions import (
    VideoProviderConfigurationError,
    VideoProviderResponseError,
)


class MinimaxH3Provider(VideoProvider):
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        output_dir: str,
        client: Optional[httpx.AsyncClient] = None,
        timeout_s: float = 300,
        poll_interval_s: float = 2,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._output_dir = output_dir
        self._client = RemoteVideoClient(client, timeout_s, poll_interval_s)

    async def generate(
        self,
        keyframe_image: str,
        prompt: str,
        duration_s: int,
        config: Mapping[str, Any],
    ) -> VideoResult:
        if duration_s < 2 or duration_s > 5:
            raise VideoProviderConfigurationError("MiniMax H3 duration must be 2-5 seconds")
        source_duration = max(duration_s, int(config.get("min_duration_s", 4)))
        image_url = keyframe_url(
            keyframe_image, str(config.get("public_asset_base_url", ""))
        )
        payload = {
            "model": self._model,
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": image_url},
                    "role": "first_frame",
                },
            ],
            "resolution": config.get("resolution", "768P"),
            "duration": source_duration,
            "ratio": config.get("ratio", "adaptive"),
            "aigc_watermark": False,
        }
        created = await self._client.post_json(
            f"{self._base_url}/v2/video_generation",
            payload,
            self._headers,
        )
        try:
            task_id = created["task_id"]
        except KeyError as error:
            raise VideoProviderResponseError("MiniMax response missing task id") from error
        url = await self._client.poll(
            f"{self._base_url}/v2/video_generation/{task_id}",
            self._headers,
            read_status=lambda payload: payload.get("task", {}).get("status", ""),
            read_url=lambda payload: payload["task"]["content"]["url"],
        )
        path = await self._client.download(url, self._output_dir, self._headers)
        return video_result(
            path, duration_s, source_duration, "minimax_h3", config, str(task_id)
        )
