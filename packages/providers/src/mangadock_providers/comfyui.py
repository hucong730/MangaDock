import uuid
from collections.abc import Sequence
from typing import Optional

import httpx

from mangadock_providers.comfyui_client import ComfyUIClientError, ComfyUIHttpClient
from mangadock_providers.image_base import ImageProvider, ImageResult
from mangadock_providers.image_exceptions import (
    ImageProviderAPIError,
    ImageProviderConfigurationError,
    ImageProviderResponseError,
    ImageProviderTimeoutError,
    ImageProviderTransportError,
)

ERROR_TYPES = {
    "configuration": ImageProviderConfigurationError,
    "transport": ImageProviderTransportError,
    "api": ImageProviderAPIError,
    "response": ImageProviderResponseError,
    "timeout": ImageProviderTimeoutError,
}


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
        self._workflow_id = workflow_id
        self._output_dir = output_dir
        self._client = ComfyUIHttpClient(
            base_url=base_url,
            api_key=api_key,
            client=client,
            timeout_s=timeout_s,
            poll_interval_s=poll_interval_s,
        )

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
        try:
            workflow = self._client.load_template(self._workflow_id)
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
                uploaded = await self._client.upload_image(filename)
                node_id = str(7 + index)
                if index == 1:
                    workflow[node_id]["inputs"]["image"] = uploaded
                else:
                    workflow[node_id] = {
                        "class_type": "LoadImage",
                        "inputs": {"image": uploaded},
                    }
                text_node["inputs"][f"images.image_{index}"] = [node_id, 0]

            prompt_id = await self._client.submit(workflow)
            metadata = await self._client.poll_media(prompt_id, ("images",))
            path = await self._client.download(metadata, self._output_dir, ".png")
        except ComfyUIClientError as error:
            raise ERROR_TYPES[error.kind](str(error)) from error
        width, height = size
        return ImageResult(
            path=path,
            width=width,
            height=height,
            format="png",
            workflow_id=self._workflow_id,
            metadata={"prompt_id": prompt_id, **metadata},
        )
