import pytest

from mangadock_persistence.models import LLMProviderRecord
from mangadock_providers import (
    FakeLLMProvider,
    OpenAICompatibleProvider,
    ProviderConfigurationError,
)
from mangadock_worker.provider_factory import provider_for_record


def record(enabled: bool = True) -> LLMProviderRecord:
    return LLMProviderRecord(
        name="test",
        base_url="https://api.example.com/v1",
        model="example-model",
        api_key_env="TEST_PROVIDER_KEY",
        enabled=enabled,
    )


def test_factory_returns_fake_in_fake_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MANGADOCK_LLM_MODE", "fake")

    provider = provider_for_record(record())

    assert isinstance(provider, FakeLLMProvider)


def test_factory_uses_selected_record_in_live_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MANGADOCK_LLM_MODE", "live")
    monkeypatch.setenv("TEST_PROVIDER_KEY", "secret-value")

    provider = provider_for_record(record())

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider._base_url == "https://api.example.com/v1"
    assert provider._model == "example-model"
    assert provider._api_key == "secret-value"


def test_factory_rejects_missing_key_without_leaking_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MANGADOCK_LLM_MODE", "live")
    monkeypatch.delenv("TEST_PROVIDER_KEY", raising=False)

    with pytest.raises(ProviderConfigurationError) as error:
        provider_for_record(record())

    assert "TEST_PROVIDER_KEY" in str(error.value)
    assert "secret-value" not in str(error.value)


def test_factory_rejects_disabled_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MANGADOCK_LLM_MODE", "fake")

    with pytest.raises(ProviderConfigurationError, match="disabled"):
        provider_for_record(record(enabled=False))


def test_factory_rejects_unknown_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MANGADOCK_LLM_MODE", "unknown")

    with pytest.raises(ProviderConfigurationError, match="MANGADOCK_LLM_MODE"):
        provider_for_record(record())
