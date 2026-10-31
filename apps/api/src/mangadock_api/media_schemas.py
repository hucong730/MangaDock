from pydantic import BaseModel, Field


class RenderRequest(BaseModel):
    video_provider_id: int | None = None
    segment_providers: dict[str, int] = Field(default_factory=dict)


class RenderStartResponse(BaseModel):
    project_id: int
    episode: int
    status: str
