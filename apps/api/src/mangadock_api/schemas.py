from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class LLMProviderBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    base_url: HttpUrl
    model: str = Field(min_length=1, max_length=255)
    api_key_env: str = Field(pattern=r"^[A-Z_][A-Z0-9_]*$", max_length=255)
    enabled: bool = True
    capabilities: list[str] = Field(default_factory=lambda: ["script"])

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("Capabilities must not be empty")
        if len(value) != len(set(value)):
            raise ValueError("Capabilities must be unique")
        if any(capability not in {"script", "image", "video"} for capability in value):
            raise ValueError("Unsupported provider capability")
        return value

    @field_validator("name", "model")
    @classmethod
    def strip_and_validate_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value must not be blank")
        return value


class LLMProviderCreate(LLMProviderBase):
    pass


class LLMProviderUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    base_url: Optional[HttpUrl] = None
    model: Optional[str] = Field(default=None, min_length=1, max_length=255)
    api_key_env: Optional[str] = Field(
        default=None,
        pattern=r"^[A-Z_][A-Z0-9_]*$",
        max_length=255,
    )
    enabled: Optional[bool] = None
    capabilities: Optional[list[str]] = None

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        if value is None:
            return value
        if not value:
            raise ValueError("Capabilities must not be empty")
        if len(value) != len(set(value)):
            raise ValueError("Capabilities must be unique")
        if any(capability not in {"script", "image", "video"} for capability in value):
            raise ValueError("Unsupported provider capability")
        return value

    @field_validator("name", "model")
    @classmethod
    def strip_and_validate_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            raise ValueError("Value must not be null")
        value = value.strip()
        if not value:
            raise ValueError("Value must not be blank")
        return value

    @field_validator("base_url", "api_key_env", "enabled", mode="before")
    @classmethod
    def reject_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("Value must not be null")
        return value


class LLMProviderRead(BaseModel):
    id: int
    name: str
    base_url: str
    model: str
    api_key_env: str
    enabled: bool
    capabilities: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
