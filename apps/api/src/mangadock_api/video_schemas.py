from datetime import datetime
from typing import Any, Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator


def validate_config(value: dict[str, Any]) -> dict[str, Any]:
    for field in ("max_concurrency", "min_duration_s"):
        if field in value and (
            not isinstance(value[field], int) or isinstance(value[field], bool) or value[field] < 1
        ):
            raise ValueError(f"{field} must be a positive integer")
    public_url = value.get("public_asset_base_url")
    if public_url and urlparse(public_url).scheme not in {"http", "https"}:
        raise ValueError("public_asset_base_url must use HTTP(S)")
    return value


class VideoProviderBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["wan", "seedance", "minimax_h3"]
    base_url: str = Field(min_length=1, max_length=2048)
    model: str = Field(min_length=1, max_length=255)
    api_key_env: str = Field(pattern=r"^[A-Z_][A-Z0-9_]*$", max_length=255)
    enabled: bool = True
    config_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("config_json")
    @classmethod
    def check_config(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_config(value)


class VideoProviderCreate(VideoProviderBase):
    pass


class VideoProviderUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    kind: Optional[Literal["wan", "seedance", "minimax_h3"]] = None
    base_url: Optional[str] = Field(default=None, min_length=1, max_length=2048)
    model: Optional[str] = Field(default=None, min_length=1, max_length=255)
    api_key_env: Optional[str] = Field(
        default=None, pattern=r"^[A-Z_][A-Z0-9_]*$", max_length=255
    )
    enabled: Optional[bool] = None
    config_json: Optional[dict[str, Any]] = None

    @field_validator("config_json")
    @classmethod
    def check_config(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_config(value) if value is not None else None


class VideoProviderRead(BaseModel):
    id: int
    name: str
    kind: str
    base_url: str
    model: str
    api_key_env: str
    enabled: bool
    config_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
