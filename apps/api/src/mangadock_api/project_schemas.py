from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StageRead(BaseModel):
    stage: str
    status: str
    completed_items: int
    total_items: int
    attempt_count: int
    requires_attention: bool
    error: str | None

    model_config = ConfigDict(from_attributes=True)


class ProviderRouteRead(BaseModel):
    role: str
    provider_id: int

    model_config = ConfigDict(from_attributes=True)


class ProjectSummary(BaseModel):
    id: int
    title: str
    source_filename: str
    source_media_type: str
    provider_id: int
    created_at: datetime
    stages: list[StageRead]
    provider_routes: list[ProviderRouteRead]


class ProjectDetail(ProjectSummary):
    novel_json: dict


class ProjectStatus(BaseModel):
    project_id: int
    stages: list[StageRead]


class RetryResponse(BaseModel):
    project_id: int
    stage: str
    status: str
