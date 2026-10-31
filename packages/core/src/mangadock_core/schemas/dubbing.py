from typing import Literal

from pydantic import Field, model_validator

from mangadock_core.schemas.base import SchemaModel


class DubbingLine(SchemaModel):
    line_id: str = Field(min_length=1)
    scene: int = Field(ge=1)
    order: int = Field(ge=1)
    segment: int = Field(ge=1)
    cut: int = Field(ge=1)
    character: str = Field(min_length=1)
    text: str = Field(min_length=1)
    emotion: str = Field(min_length=1)
    audio_path: str | None = None
    start_s: float = Field(default=0, ge=0)
    duration_s: float = Field(default=0, ge=0)
    end_s: float = Field(default=0, ge=0)
    status: Literal["pending", "running", "done", "failed"] = "pending"
    error: str | None = None

    @model_validator(mode="after")
    def validate_timing(self) -> "DubbingLine":
        if abs(self.end_s - (self.start_s + self.duration_s)) > 0.001:
            raise ValueError("end_s must equal start_s plus duration_s")
        if self.status == "done" and not self.audio_path:
            raise ValueError("Done dubbing lines require audio_path")
        return self


class DubbingEpisode(SchemaModel):
    episode: int = Field(ge=1)
    source_fingerprint: str = ""
    lines: list[DubbingLine]


class Dubbing(SchemaModel):
    episodes: list[DubbingEpisode] = Field(min_length=1)
