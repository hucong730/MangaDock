import json
from typing import Any

import httpx
import pytest
import respx
from pydantic import BaseModel

from mangadock_providers import (
    LLMProvider,
    OpenAICompatibleProvider,
    ProviderAPIError,
    ProviderConfigurationError,
    ProviderError,
    ProviderResponseError,
    ProviderTransportError,
)

API_KEY = "test-secret-key"
MESSAGES = [
    {"role": "system", "content": "Return a scene"},
    {"role": "user", "content": "A rainy station"},
]


class Scene(BaseModel):
    title: str
    shot_count: int


class SceneDetails(BaseModel):
    location: str


class SceneWithOptional(BaseModel):
    title: str
    subtitle: str | None = None
    details: SceneDetails
    shots: list[SceneDetails]


def upstream_response(content: object) -> dict[str, Any]:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": content,
                }
            }
        ]
    }


def make_provider(
    client: httpx.AsyncClient,
    base_url: str = "https://api.example.com/v1",
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        base_url=base_url,
        api_key=API_KEY,
        model="example-model",
        client=client,
    )


def test_provider_contract_is_abstract_and_exceptions_are_stable() -> None:
    with pytest.raises(TypeError):
        LLMProvider()

    for exception_type in (
        ProviderConfigurationError,
        ProviderTransportError,
        ProviderAPIError,
        ProviderResponseError,
    ):
        assert issubclass(exception_type, ProviderError)


@pytest.mark.asyncio
async def test_from_env_sends_strict_structured_output_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", API_KEY)
    monkeypatch.setenv("OPENAI_MODEL", "example-model")
    expected_content = json.dumps({"title": "Rain", "shot_count": 3})

    async with httpx.AsyncClient() as client:
        provider = OpenAICompatibleProvider.from_env(client=client)
        with respx.mock(assert_all_called=True) as mock:
            route = mock.post("https://api.example.com/v1/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    json=upstream_response(expected_content),
                )
            )

            result = await provider.chat(MESSAGES, Scene)

    assert isinstance(result, Scene)
    assert result == Scene(title="Rain", shot_count=3)
    request = route.calls.last.request
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    body = json.loads(request.content)
    assert body["model"] == "example-model"
    assert body["messages"] == MESSAGES
    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "Scene",
            "strict": True,
            "schema": {
                **Scene.model_json_schema(),
                "additionalProperties": False,
            },
        },
    }


@pytest.mark.asyncio
async def test_strict_schema_handles_nested_and_optional_models() -> None:
    output = {
        "title": "Rain",
        "subtitle": None,
        "details": {"location": "Tokyo"},
        "shots": [{"location": "Platform"}],
    }
    async with httpx.AsyncClient() as client:
        provider = make_provider(client)
        with respx.mock(assert_all_called=True) as mock:
            route = mock.post("https://api.example.com/v1/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    json=upstream_response(json.dumps(output)),
                )
            )
            result = await provider.chat(MESSAGES, SceneWithOptional)

    assert isinstance(result, SceneWithOptional)
    body = json.loads(route.calls.last.request.content)
    schema = body["response_format"]["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"title", "subtitle", "details", "shots"}
    assert "default" not in schema["properties"]["subtitle"]
    assert schema["properties"]["subtitle"]["anyOf"] == [
        {"type": "string"},
        {"type": "null"},
    ]
    nested = schema["$defs"]["SceneDetails"]
    assert nested["additionalProperties"] is False
    assert nested["required"] == ["location"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("base_url", "expected_url"),
    [
        ("https://api.example.com", "https://api.example.com/chat/completions"),
        ("https://api.example.com/", "https://api.example.com/chat/completions"),
        ("https://api.example.com/v1/", "https://api.example.com/v1/chat/completions"),
    ],
)
async def test_base_url_is_normalized(
    base_url: str,
    expected_url: str,
) -> None:
    async with httpx.AsyncClient() as client:
        provider = make_provider(client, base_url=base_url)
        with respx.mock(assert_all_called=True) as mock:
            route = mock.post(expected_url).mock(
                return_value=httpx.Response(
                    200,
                    json=upstream_response('{"title":"Rain","shot_count":3}'),
                )
            )
            await provider.chat(MESSAGES, Scene)

    assert route.called


@pytest.mark.parametrize("missing", ["OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL"])
def test_from_env_requires_configuration(
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
) -> None:
    values = {
        "OPENAI_BASE_URL": "https://api.example.com/v1",
        "OPENAI_API_KEY": API_KEY,
        "OPENAI_MODEL": "example-model",
    }
    for name, value in values.items():
        if name == missing:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)

    with pytest.raises(ProviderConfigurationError, match=missing) as error:
        OpenAICompatibleProvider.from_env()

    assert API_KEY not in str(error.value)


@pytest.mark.asyncio
async def test_transport_error_has_stable_type() -> None:
    async with httpx.AsyncClient() as client:
        provider = make_provider(client)
        with respx.mock(assert_all_called=True) as mock:
            mock.post("https://api.example.com/v1/chat/completions").mock(
                side_effect=httpx.ConnectError("offline")
            )
            with pytest.raises(ProviderTransportError) as error:
                await provider.chat(MESSAGES, Scene)

    assert API_KEY not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 500])
async def test_http_error_has_stable_type(status_code: int) -> None:
    async with httpx.AsyncClient() as client:
        provider = make_provider(client)
        with respx.mock(assert_all_called=True) as mock:
            mock.post("https://api.example.com/v1/chat/completions").mock(
                return_value=httpx.Response(status_code, json={"error": "failed"})
            )
            with pytest.raises(ProviderAPIError, match=str(status_code)) as error:
                await provider.chat(MESSAGES, Scene)

    assert API_KEY not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "match"),
    [
        (httpx.Response(200, text="not-json"), "response"),
        (httpx.Response(200, json={}), "response"),
        (httpx.Response(200, json={"choices": []}), "response"),
        (httpx.Response(200, json=upstream_response(None)), "content"),
        (httpx.Response(200, json=upstream_response({"title": "Rain"})), "content"),
        (httpx.Response(200, json=upstream_response("not-json")), "JSON"),
        (
            httpx.Response(
                200,
                json=upstream_response('{"title":"Rain","shot_count":"many"}'),
            ),
            "schema",
        ),
    ],
)
async def test_invalid_upstream_output_is_rejected(
    response: httpx.Response,
    match: str,
) -> None:
    async with httpx.AsyncClient() as client:
        provider = make_provider(client)
        with respx.mock(assert_all_called=True) as mock:
            mock.post("https://api.example.com/v1/chat/completions").mock(
                return_value=response
            )
            with pytest.raises(ProviderResponseError, match=match) as error:
                await provider.chat(MESSAGES, Scene)

    assert API_KEY not in str(error.value)
