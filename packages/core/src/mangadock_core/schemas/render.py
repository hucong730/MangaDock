from typing import Literal

from pydantic import Field, model_validator

from mangadock_core.schemas.base import SchemaModel


class RenderClip(SchemaModel):
    index: int = Field(ge=1)
    duration_s: int = Field(ge=2, le=5)
    status: Literal["pending", "running", "done", "failed", "outdated"] = "pending"
    attempt_count: int = Field(default=0, ge=0)
    provider_id: int | None = None
    clip_path: str | None = None
    source_duration_s: float | None = Field(default=None, ge=0)
    source_fingerprint: str = ""
    error: str | None = None

    @model_validator(mode="after")
    def validate_clip(self) -> "RenderClip":
        if self.status == "done" and not self.clip_path:
            raise ValueError("Done render clips require clip_path")
        return self


class RenderSegment(SchemaModel):
    index: int = Field(ge=1)
    cuts: list[RenderClip] = Field(min_length=1)


class RenderEpisode(SchemaModel):
    episode: int = Field(ge=1)
    segments: list[RenderSegment] = Field(min_length=1)


class Render(SchemaModel):
    episodes: list[RenderEpisode] = Field(min_length=1)
