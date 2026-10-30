import asyncio
import json
import os
import time
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Optional

import httpx

from mangadock_providers.image_base import ImageProvider, ImageResult
from mangadock_providers.image_exceptions import (
    ImageProviderAPIError,
    ImageProviderConfigurationError,
    ImageProviderResponseError,
    ImageProviderTimeoutError,
    ImageProviderTransportError,
)


class ComfyUIProvider(ImageProvider):
    def __init__(
        self,
        base_url: str,
        workflow_id: str,
        output_dir: str,
        api_key: str = "",
        client: Optional[httpx.AsyncClient] = None,
        timeout_s: float = 300,
        poll_interval_s: float = 2,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._workflow_id = workflow_id
        self._output_dir = Path(output_dir)
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=60)
        self._timeout_s = timeout_s
        self._poll_interval_s = poll_interval_s

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}

    def _load_template(self) -> dict[str, Any]:
        template_dir = Path(
            os.getenv(
                "COMFYUI_TEMPLATE_DIR",
                str(Path(__file__).parents[2] / "comfyui" / "templates"),
            )
        )
        return json.loads(
            (template_dir / f"{self._workflow_id}.json").read_text(encoding="utf-8")
        )

    async def _upload_reference(self, filename: str) -> str:
        path = Path(filename)
        try:
            response = await self._client.post(
                f"{self._base_url}/upload/image",
                headers=self._headers(),
                data={"overwrite": "true", "type": "input"},
                files={"image": (path.name, path.read_bytes(), "image/png")},
            )
        except httpx.HTTPError as error:
            raise ImageProviderTransportError("Failed to upload reference image") from error
        if response.status_code >= 400:
            raise ImageProviderAPIError(
                f"ComfyUI upload returned HTTP {response.status_code}"
            )
        payload = response.json()
        subfolder = payload.get("subfolder", "")
        name = payload.get("name", path.name)
        return f"{subfolder}/{name}" if subfolder else name

    async def generate(
        self,
        prompt: str,
        reference_images: Sequence[str],
        size: tuple[int, int],
    ) -> ImageResult:
        if len(reference_images) > 4:
            raise ImageProviderConfigurationError(
                "ComfyUI supports at most 4 reference images"
            )
        workflow = self._load_template()
        text_node = next(
            node
            for node in workflow.values()
            if node["class_type"] == "TextEncodeQwenImage21"
        )
        text_node["inputs"]["prompt"] = prompt
        text_node["inputs"]["negative_prompt"] = (
            "blurry, low quality, distorted facial features, changed identity"
        )
        text_node["inputs"]["resolution"] = max(size)
        sampler = next(
            node for node in workflow.values() if node["class_type"] == "KSampler"
        )
        sampler["inputs"]["seed"] = uuid.uuid4().int % (2**31)

        for index, filename in enumerate(reference_images, start=1):
            uploaded = await self._upload_reference(filename)
            node_id = str(7 + index)
            if index == 1:
                workflow[node_id]["inputs"]["image"] = uploaded
            else:
                workflow[node_id] = {
                    "class_type": "LoadImage",
                    "inputs": {"image": uploaded},
                }
            text_node["inputs"][f"images.image_{index}"] = [node_id, 0]

        try:
            response = await self._client.post(
                f"{self._base_url}/prompt",
                headers=self._headers(),
                json={"prompt": workflow, "client_id": uuid.uuid4().hex},
            )
        except httpx.HTTPError as error:
            raise ImageProviderTransportError("Failed to submit ComfyUI workflow") from error
        if response.status_code >= 400:
            raise ImageProviderAPIError(
                f"ComfyUI prompt returned HTTP {response.status_code}"
            )
        try:
            prompt_id = response.json()["prompt_id"]
        except (KeyError, ValueError) as error:
            raise ImageProviderResponseError("ComfyUI prompt response missing prompt_id") from error

        image_metadata = await self._poll_result(prompt_id)
        try:
            response = await self._client.get(
                f"{self._base_url}/view",
                headers=self._headers(),
                params={
                    "filename": image_metadata["filename"],
                    "subfolder": image_metadata.get("subfolder", ""),
                    "type": image_metadata.get("type", "output"),
                },
            )
        except httpx.HTTPError as error:
            raise ImageProviderTransportError("Failed to download ComfyUI image") from error
        if response.status_code >= 400:
            raise ImageProviderAPIError(
                f"ComfyUI view returned HTTP {response.status_code}"
            )

        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / f"{uuid.uuid4().hex}.png"
        path.write_bytes(response.content)
        width, height = size
        return ImageResult(
            path=path,
            width=width,
            height=height,
            format="png",
            workflow_id=self._workflow_id,
            metadata={"prompt_id": prompt_id, **image_metadata},
        )

    async def _poll_result(self, prompt_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self._timeout_s
        while True:
            try:
                response = await self._client.get(
                    f"{self._base_url}/history/{prompt_id}",
                    headers=self._headers(),
                )
            except httpx.HTTPError as error:
                raise ImageProviderTransportError("Failed to poll ComfyUI history") from error
            if response.status_code >= 400:
                raise ImageProviderAPIError(
                    f"ComfyUI history returned HTTP {response.status_code}"
                )
            try:
                payload = response.json()
            except ValueError as error:
                raise ImageProviderResponseError("Invalid ComfyUI history response") from error
            history = payload.get(prompt_id) if isinstance(payload, dict) else None
            if history is not None and not isinstance(history, dict):
                raise ImageProviderResponseError("Invalid ComfyUI history response")
            if history is not None:
                status = history.get("status", {}).get("status_str", "")
                if status in {"error", "failed"}:
                    raise ImageProviderResponseError("ComfyUI workflow failed")
                outputs = history.get("outputs", {})
                for node_output in outputs.values():
                    images = node_output.get("images", [])
                    if images:
                        return images[0]
                if status == "success":
                    raise ImageProviderResponseError("ComfyUI returned no output images")
            if time.monotonic() >= deadline:
                raise ImageProviderTimeoutError("ComfyUI workflow timed out")
            await asyncio.sleep(self._poll_interval_s)
