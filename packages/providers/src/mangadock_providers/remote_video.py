import asyncio
import base64
import os
import time
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import httpx

from mangadock_providers.video_base import VideoResult
from mangadock_providers.video_exceptions import (
    VideoProviderAPIError,
    VideoProviderConfigurationError,
    VideoProviderResponseError,
    VideoProviderTimeoutError,
    VideoProviderTransportError,
)


def keyframe_url(keyframe_image: str, public_asset_base_url: str = "") -> str:
    if public_asset_base_url:
        path = Path(keyframe_image)
        if path.is_absolute():
            try:
                relative_path = path.resolve().relative_to(
                    Path(os.getenv("ASSET_ROOT", "assets")).resolve()
                )
            except ValueError:
                relative_path = Path(path.name)
        else:
            relative_path = path
        relative = relative_path.as_posix().lstrip("/")
        return f"{public_asset_base_url.rstrip('/')}/{quote(relative)}"
    path = Path(keyframe_image)
    try:
        content = path.read_bytes()
    except OSError as error:
        raise VideoProviderConfigurationError(
            f"Unable to read keyframe image {keyframe_image}"
        ) from error
    if len(content) > 30 * 1024 * 1024:
        raise VideoProviderConfigurationError("Keyframe image exceeds 30MB")
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "image/png")
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime};base64,{encoded}"


class RemoteVideoClient:
    def __init__(
        self,
        client: Optional[httpx.AsyncClient],
        timeout_s: float,
        poll_interval_s: float,
    ) -> None:
        self._client = client or httpx.AsyncClient(timeout=60)
        self._timeout_s = timeout_s
        self._poll_interval_s = poll_interval_s

    async def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        return await self._request("POST", url, payload, headers)

    async def get_json(self, url: str, headers: dict[str, str]) -> dict[str, Any]:
        return await self._request("GET", url, None, headers)

    async def _request(
        self,
        method: str,
        url: str,
        payload: dict[str, Any] | None,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        try:
            response = await self._client.request(
                method, url, json=payload, headers=headers
            )
        except httpx.HTTPError as error:
            raise VideoProviderTransportError(f"{method} {url} failed") from error
        if response.status_code >= 400:
            raise VideoProviderAPIError(
                f"Video API returned HTTP {response.status_code}"
            )
        try:
            value = response.json()
        except ValueError as error:
            raise VideoProviderResponseError("Video API returned invalid JSON") from error
        if not isinstance(value, dict):
            raise VideoProviderResponseError("Video API returned a non-object response")
        return value

    async def poll(
        self,
        task_url: str,
        headers: dict[str, str],
        read_status: Callable[[dict[str, Any]], str],
        read_url: Callable[[dict[str, Any]], str],
    ) -> str:
        deadline = time.monotonic() + self._timeout_s
        while True:
            payload = await self.get_json(task_url, headers)
            try:
                status = read_status(payload)
                if status == "succeeded":
                    return read_url(payload)
            except (KeyError, TypeError) as error:
                raise VideoProviderResponseError(
                    "Video task response is missing status or output URL"
                ) from error
            if status in {"failed", "error", "cancelled"}:
                raise VideoProviderResponseError("Video generation task failed")
            if time.monotonic() >= deadline:
                raise VideoProviderTimeoutError("Video generation task timed out")
            await asyncio.sleep(self._poll_interval_s)

    async def download(
        self,
        url: str,
        output_dir: str,
        headers: dict[str, str],
    ) -> str:
        try:
            response = await self._client.get(url, headers=headers)
        except httpx.HTTPError as error:
            raise VideoProviderTransportError("Failed to download generated video") from error
        if response.status_code >= 400:
            raise VideoProviderAPIError(
                f"Video download returned HTTP {response.status_code}"
            )
        directory = Path(output_dir)
        try:
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{uuid.uuid4().hex}.mp4"
            path.write_bytes(response.content)
        except OSError as error:
            raise VideoProviderConfigurationError("Unable to store generated video") from error
        return str(path)


def video_result(
    path: str,
    duration_s: int,
    source_duration_s: int,
    provider: str,
    config: Mapping[str, Any],
    task_id: str,
) -> VideoResult:
    return VideoResult(
        path=path,
        duration_s=duration_s,
        source_duration_s=source_duration_s,
        width=int(config.get("width", 1920)),
        height=int(config.get("height", 1080)),
        format="mp4",
        provider=provider,
        metadata={"task_id": task_id},
    )
