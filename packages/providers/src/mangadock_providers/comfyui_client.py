import asyncio
import json
import os
import time
import uuid
from collections.abc import Collection
from pathlib import Path
from typing import Any, Literal, Optional

import httpx


class ComfyUIClientError(Exception):
    def __init__(
        self,
        kind: Literal["configuration", "transport", "api", "response", "timeout"],
        message: str,
    ) -> None:
        super().__init__(message)
        self.kind = kind


class ComfyUIHttpClient:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        client: Optional[httpx.AsyncClient] = None,
        timeout_s: float = 300,
        poll_interval_s: float = 2,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=60)
        self._timeout_s = timeout_s
        self._poll_interval_s = poll_interval_s

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}

    def load_template(self, workflow_id: str) -> dict[str, Any]:
        template_dir = Path(
            os.getenv(
                "COMFYUI_TEMPLATE_DIR",
                str(Path(__file__).parents[2] / "comfyui" / "templates"),
            )
        )
        try:
            return json.loads(
                (template_dir / f"{workflow_id}.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as error:
            raise ComfyUIClientError(
                "configuration", f"Unable to load ComfyUI template {workflow_id}"
            ) from error

    async def upload_image(self, filename: str) -> str:
        path = Path(filename)
        try:
            content = path.read_bytes()
        except OSError as error:
            raise ComfyUIClientError(
                "configuration", f"Unable to read keyframe image {filename}"
            ) from error
        try:
            response = await self._client.post(
                f"{self._base_url}/upload/image",
                headers=self._headers(),
                data={"overwrite": "true", "type": "input"},
                files={"image": (path.name, content, "image/png")},
            )
        except httpx.HTTPError as error:
            raise ComfyUIClientError(
                "transport", "Failed to upload reference image"
            ) from error
        if response.status_code >= 400:
            raise ComfyUIClientError(
                "api", f"ComfyUI upload returned HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise ComfyUIClientError("response", "Invalid ComfyUI upload response") from error
        subfolder = payload.get("subfolder", "")
        name = payload.get("name", path.name)
        return f"{subfolder}/{name}" if subfolder else name

    async def submit(self, workflow: dict[str, Any]) -> str:
        try:
            response = await self._client.post(
                f"{self._base_url}/prompt",
                headers=self._headers(),
                json={"prompt": workflow, "client_id": uuid.uuid4().hex},
            )
        except httpx.HTTPError as error:
            raise ComfyUIClientError("transport", "Failed to submit ComfyUI workflow") from error
        if response.status_code >= 400:
            raise ComfyUIClientError(
                "api", f"ComfyUI prompt returned HTTP {response.status_code}"
            )
        try:
            return response.json()["prompt_id"]
        except (KeyError, TypeError, ValueError) as error:
            raise ComfyUIClientError(
                "response", "ComfyUI prompt response missing prompt_id"
            ) from error

    async def poll_media(
        self,
        prompt_id: str,
        media_kinds: Collection[str],
    ) -> dict[str, Any]:
        deadline = time.monotonic() + self._timeout_s
        while True:
            try:
                response = await self._client.get(
                    f"{self._base_url}/history/{prompt_id}",
                    headers=self._headers(),
                )
            except httpx.HTTPError as error:
                raise ComfyUIClientError("transport", "Failed to poll ComfyUI history") from error
            if response.status_code >= 400:
                raise ComfyUIClientError(
                    "api", f"ComfyUI history returned HTTP {response.status_code}"
                )
            try:
                payload = response.json()
            except ValueError as error:
                raise ComfyUIClientError("response", "Invalid ComfyUI history response") from error
            history = payload.get(prompt_id) if isinstance(payload, dict) else None
            if history is not None and not isinstance(history, dict):
                raise ComfyUIClientError("response", "Invalid ComfyUI history response")
            if history is not None:
                status = history.get("status", {}).get("status_str", "")
                if status in {"error", "failed"}:
                    raise ComfyUIClientError("response", "ComfyUI workflow failed")
                outputs = history.get("outputs", {})
                for node_output in outputs.values():
                    for kind in media_kinds:
                        media = node_output.get(kind, [])
                        if media:
                            return media[0]
                if status == "success":
                    raise ComfyUIClientError("response", "ComfyUI returned no output media")
            if time.monotonic() >= deadline:
                raise ComfyUIClientError("timeout", "ComfyUI workflow timed out")
            await asyncio.sleep(self._poll_interval_s)

    async def download(
        self,
        metadata: dict[str, Any],
        output_dir: str,
        suffix: str,
    ) -> Path:
        try:
            response = await self._client.get(
                f"{self._base_url}/view",
                headers=self._headers(),
                params={
                    "filename": metadata["filename"],
                    "subfolder": metadata.get("subfolder", ""),
                    "type": metadata.get("type", "output"),
                },
            )
        except (httpx.HTTPError, KeyError) as error:
            raise ComfyUIClientError("transport", "Failed to download ComfyUI media") from error
        if response.status_code >= 400:
            raise ComfyUIClientError(
                "api", f"ComfyUI view returned HTTP {response.status_code}"
            )
        directory = Path(output_dir)
        try:
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{uuid.uuid4().hex}{suffix}"
            path.write_bytes(response.content)
        except OSError as error:
            raise ComfyUIClientError("configuration", "Unable to store ComfyUI media") from error
        return path
