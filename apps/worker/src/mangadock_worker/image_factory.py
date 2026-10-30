import os

from mangadock_persistence.models import LLMProviderRecord
from mangadock_providers import ComfyUIProvider, ImageProvider, MockImageProvider


def image_provider_for_record(
    record: LLMProviderRecord | None,
    workflow_id: str,
    output_dir: str,
) -> ImageProvider:
    mode = os.getenv(
        "MANGADOCK_IMAGE_MODE",
        os.getenv("MANGADOCK_LLM_MODE", "fake"),
    ).lower()
    if mode == "fake":
        return MockImageProvider(output_dir=output_dir, workflow_id=workflow_id)
    if mode != "live":
        raise ValueError("MANGADOCK_IMAGE_MODE must be fake or live")
    if record is None:
        raise ValueError("Image provider route is not configured")
    return ComfyUIProvider(
        base_url=record.base_url,
        workflow_id=workflow_id,
        output_dir=output_dir,
        api_key=os.getenv(record.api_key_env, ""),
    )
