import json
import os
from collections.abc import Mapping, Sequence
from typing import Any, Optional

import httpx
from pydantic import ValidationError

from mangadock_providers.base import LLMProvider, ModelT
from mangadock_providers.exceptions import (
    ProviderAPIError,
    ProviderConfigurationError,
    ProviderResponseError,
    ProviderTransportError,
)


def _strict_json_schema(node: dict[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in node.items() if key != "default"}
    if "$defs" in result:
        result["$defs"] = {
            name: _strict_json_schema(definition)
            for name, definition in result["$defs"].items()
        }
    if "properties" in result:
        result["properties"] = {
            name: _strict_json_schema(property_schema)
            for name, property_schema in result["properties"].items()
        }
        result["required"] = list(result["properties"])
        result["additionalProperties"] = False
    if "items" in result:
        result["items"] = _strict_json_schema(result["items"])
    for union_key in ("anyOf", "oneOf", "allOf"):
        if union_key in result:
            result[union_key] = [
                _strict_json_schema(option) for option in result[union_key]
            ]
    return result


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.AsyncClient(timeout=60.0)

    @classmethod
    def from_env(
        cls,
        client: Optional[httpx.AsyncClient] = None,
    ) -> "OpenAICompatibleProvider":
        values = {}
        for name in ("OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL"):
            value = os.getenv(name)
            if not value:
                raise ProviderConfigurationError(
                    f"Missing environment variable: {name}"
                )
            values[name] = value
        return cls(
            base_url=values["OPENAI_BASE_URL"],
            api_key=values["OPENAI_API_KEY"],
            model=values["OPENAI_MODEL"],
            client=client,
        )

    async def chat(
        self,
        messages: Sequence[Mapping[str, str]],
        schema: type[ModelT],
    ) -> ModelT:
        try:
            response = await self._client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "messages": [dict(message) for message in messages],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": schema.__name__,
                            "strict": True,
                            "schema": _strict_json_schema(schema.model_json_schema()),
                        },
                    },
                },
            )
        except httpx.HTTPError as error:
            raise ProviderTransportError(
                "OpenAI-compatible API request failed"
            ) from error

        if response.status_code >= 400:
            raise ProviderAPIError(
                f"OpenAI-compatible API returned HTTP {response.status_code}"
            )

        try:
            payload = response.json()
        except ValueError as error:
            raise ProviderResponseError("Invalid provider response JSON") from error

        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderResponseError("Invalid provider response structure") from error
        if not isinstance(content, str):
            raise ProviderResponseError("Invalid provider message content")

        try:
            output = json.loads(content)
        except json.JSONDecodeError as error:
            raise ProviderResponseError("Provider output is not valid JSON") from error

        try:
            return schema.model_validate(output)
        except ValidationError as error:
            raise ProviderResponseError(
                "Provider output does not match schema"
            ) from error
