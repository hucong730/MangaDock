import os

from mangadock_persistence.models import LLMProviderRecord
from mangadock_providers import (
    FakeLLMProvider,
    LLMProvider,
    OpenAICompatibleProvider,
    ProviderConfigurationError,
)


def provider_for_record(record: LLMProviderRecord) -> LLMProvider:
    if not record.enabled:
        raise ProviderConfigurationError("Selected provider is disabled")

    mode = os.getenv("MANGADOCK_LLM_MODE", "fake").lower()
    if mode == "fake":
        return FakeLLMProvider()
    if mode != "live":
        raise ProviderConfigurationError(
            "MANGADOCK_LLM_MODE must be either fake or live"
        )

    api_key = os.getenv(record.api_key_env)
    if not api_key:
        raise ProviderConfigurationError(
            f"Missing environment variable: {record.api_key_env}"
        )
    return OpenAICompatibleProvider(
        base_url=record.base_url,
        api_key=api_key,
        model=record.model,
    )
