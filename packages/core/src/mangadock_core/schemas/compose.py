from typing import Literal

from pydantic import Field, model_validator

from mangadock_core.schemas.base import SchemaModel


class EpisodeExport(SchemaModel):
    episode: int = Field(ge=1)
    status: Literal["pending", "running", "done", "failed", "outdated"] = "pending"
    burned_path: str | None = None
    clean_path: str | None = None
    srt_path: str | None = None
    vtt_path: str | None = None
    duration_s: float = Field(default=0, ge=0)
    width: int = Field(default=1920, ge=1)
    height: int = Field(default=1080, ge=1)
    source_fingerprint: str = ""
    error: str | None = None

    @model_validator(mode="after")
    def validate_export(self) -> "EpisodeExport":
        if self.status == "done" and not all(
            [self.burned_path, self.clean_path, self.srt_path, self.vtt_path]
        ):
            raise ValueError("Done exports require burned_path, clean_path, srt_path, and vtt_path")
        return self


class Compose(SchemaModel):
    episodes: list[EpisodeExport] = Field(min_length=1)
