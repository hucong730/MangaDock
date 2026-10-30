from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from mangadock_api.config import settings
from mangadock_api.database import get_db
from mangadock_api.models import (
    LLMProviderRecord,
    ProjectEpisodeRecord,
    ProjectProviderRouteRecord,
    ProjectRecord,
    ProjectStageRecord,
)
from mangadock_api.project_schemas import (
    ProjectDetail,
    ProjectStatus,
    ProjectSummary,
    ProviderRouteRead,
    RetryResponse,
    StageRead,
)
from mangadock_api.routers.providers import get_capabilities
from mangadock_api.queue import enqueue_task
from mangadock_core.parsing import NovelParseError, parse_novel

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


async def get_project(session: AsyncSession, project_id: int) -> ProjectRecord:
    project = await session.get(ProjectRecord, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


async def get_stages(
    session: AsyncSession,
    project_id: int,
) -> list[ProjectStageRecord]:
    result = await session.scalars(
        select(ProjectStageRecord)
        .where(ProjectStageRecord.project_id == project_id)
        .order_by(ProjectStageRecord.id)
    )
    return list(result.all())


def stage_read(stage: ProjectStageRecord) -> StageRead:
    return StageRead.model_validate(stage)


async def get_routes(
    session: AsyncSession,
    project_id: int,
) -> list[ProjectProviderRouteRecord]:
    result = await session.scalars(
        select(ProjectProviderRouteRecord)
        .where(ProjectProviderRouteRecord.project_id == project_id)
        .order_by(ProjectProviderRouteRecord.id)
    )
    return list(result.all())


async def validate_route_provider(
    session: AsyncSession,
    provider_id: int,
    role: str,
) -> None:
    provider = await session.get(
        LLMProviderRecord,
        provider_id,
        with_for_update=True,
    )
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider 不存在")
    if not provider.enabled:
        raise HTTPException(status_code=409, detail="Provider 已停用")
    capabilities = await get_capabilities(session, provider_id)
    if role not in capabilities:
        raise HTTPException(
            status_code=409,
            detail=f"Provider 不具备 {role} 能力",
        )


def project_summary(
    project: ProjectRecord,
    stages: list[ProjectStageRecord],
    routes: list[ProjectProviderRouteRecord],
) -> ProjectSummary:
    return ProjectSummary(
        id=project.id,
        title=project.title,
        source_filename=project.source_filename,
        source_media_type=project.source_media_type,
        provider_id=project.provider_id,
        created_at=project.created_at,
        stages=[stage_read(stage) for stage in stages],
        provider_routes=[ProviderRouteRead.model_validate(route) for route in routes],
    )


async def project_detail(
    session: AsyncSession,
    project: ProjectRecord,
) -> ProjectDetail:
    stages = await get_stages(session, project.id)
    routes = await get_routes(session, project.id)
    return ProjectDetail(
        **project_summary(project, stages, routes).model_dump(),
        novel_json=project.novel_json,
    )


@router.post("", response_model=ProjectDetail, status_code=201)
async def create_project(
    provider_id: int = Form(...),
    image_provider_id: int | None = Form(None),
    video_provider_id: int | None = Form(None),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    await file.close()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件大小不能超过 20MB")

    route_requests = [("script", provider_id)]
    if image_provider_id is not None:
        route_requests.append(("image", image_provider_id))
    if video_provider_id is not None:
        route_requests.append(("video", video_provider_id))
    for role, route_provider_id in sorted(route_requests, key=lambda item: item[1]):
        await validate_route_provider(session, route_provider_id, role)

    try:
        novel = parse_novel(file.filename or "novel", content)
    except NovelParseError as error:
        status_code = 415 if error.code == "unsupported" else 422
        raise HTTPException(status_code=status_code, detail=str(error)) from error

    character_count = sum(len(chapter.text) for chapter in novel.chapters)
    if character_count > settings.max_novel_chars:
        raise HTTPException(
            status_code=422,
            detail=f"小说文本超过当前生成上限（{settings.max_novel_chars} 字符）",
        )

    project = ProjectRecord(
        title=novel.title,
        source_filename=file.filename or novel.title,
        source_media_type=file.content_type or "application/octet-stream",
        provider_id=provider_id,
        novel_json=novel.model_dump(mode="json"),
    )
    session.add(project)
    await session.flush()
    session.add(
        ProjectProviderRouteRecord(
            project_id=project.id,
            role="script",
            provider_id=provider_id,
        )
    )
    if image_provider_id is not None:
        session.add(
            ProjectProviderRouteRecord(
                project_id=project.id,
                role="image",
                provider_id=image_provider_id,
            )
        )
    if video_provider_id is not None:
        session.add(
            ProjectProviderRouteRecord(
                project_id=project.id,
                role="video",
                provider_id=video_provider_id,
            )
        )
    outline_stage = ProjectStageRecord(
        project_id=project.id,
        stage="outline",
        total_items=1,
    )
    script_stage = ProjectStageRecord(project_id=project.id, stage="script")
    session.add_all([outline_stage, script_stage])
    await session.commit()
    await session.refresh(project)

    try:
        enqueue_task("mangadock_worker.tasks.stage_outline", project.id)
    except Exception:
        outline_stage.status = "failed"
        outline_stage.requires_attention = True
        outline_stage.error = "任务入队失败，请重试"
        await session.commit()

    return await project_detail(session, project)


@router.get("", response_model=list[ProjectSummary])
async def list_projects(
    session: AsyncSession = Depends(get_db),
) -> list[ProjectSummary]:
    projects = list(
        (
            await session.scalars(
                select(ProjectRecord).order_by(ProjectRecord.created_at.desc())
            )
        ).all()
    )
    summaries = []
    for project in projects:
        stages = await get_stages(session, project.id)
        routes = await get_routes(session, project.id)
        summaries.append(project_summary(project, stages, routes))
    return summaries


@router.get("/{project_id}", response_model=ProjectDetail)
async def read_project(
    project_id: int,
    session: AsyncSession = Depends(get_db),
) -> ProjectDetail:
    project = await get_project(session, project_id)
    return await project_detail(session, project)


@router.get("/{project_id}/status", response_model=ProjectStatus)
async def project_status(
    project_id: int,
    session: AsyncSession = Depends(get_db),
) -> ProjectStatus:
    await get_project(session, project_id)
    stages = await get_stages(session, project_id)
    upload_stage = StageRead(
        stage="upload",
        status="done",
        completed_items=1,
        total_items=1,
        attempt_count=1,
        requires_attention=False,
        error=None,
    )
    return ProjectStatus(
        project_id=project_id,
        stages=[upload_stage, *[stage_read(stage) for stage in stages]],
    )


@router.get("/{project_id}/outline")
async def project_outline(
    project_id: int,
    session: AsyncSession = Depends(get_db),
) -> dict:
    project = await get_project(session, project_id)
    if project.outline_json is None:
        raise HTTPException(status_code=409, detail="Outline 尚未生成")
    return project.outline_json


@router.get("/{project_id}/script")
async def project_script(
    project_id: int,
    session: AsyncSession = Depends(get_db),
) -> dict:
    project = await get_project(session, project_id)
    if project.script_json is None:
        raise HTTPException(status_code=409, detail="Script 尚未生成")
    return project.script_json


@router.post("/{project_id}/stages/{stage}/retry", response_model=RetryResponse, status_code=202)
async def retry_stage(
    project_id: int,
    stage: str,
    session: AsyncSession = Depends(get_db),
) -> RetryResponse:
    if stage not in {"outline", "script"}:
        raise HTTPException(status_code=422, detail="不支持的重试阶段")
    project = await get_project(session, project_id)
    stages = await get_stages(session, project_id)
    stage_map = {record.stage: record for record in stages}
    current = stage_map[stage]
    if current.status != "failed":
        raise HTTPException(status_code=409, detail="仅失败阶段可以重试")

    if stage == "outline":
        project.outline_json = None
        project.script_json = None
        await session.execute(
            delete(ProjectEpisodeRecord).where(
                ProjectEpisodeRecord.project_id == project_id
            )
        )
        script = stage_map["script"]
        script.status = "pending"
        script.completed_items = 0
        script.total_items = 0
        script.attempt_count = 0
        script.error = None
        script.requires_attention = False
        task_name = "mangadock_worker.tasks.stage_outline"
    else:
        if project.outline_json is None:
            raise HTTPException(status_code=409, detail="Outline 尚未完成")
        project.script_json = None
        episodes = list(
            (
                await session.scalars(
                    select(ProjectEpisodeRecord).where(
                        ProjectEpisodeRecord.project_id == project_id
                    )
                )
            ).all()
        )
        for episode in episodes:
            episode.status = "pending"
            episode.attempt_count = 0
            episode.error = None
            episode.payload_json = None
        task_name = "mangadock_worker.tasks.start_script"

    current.status = "pending"
    current.completed_items = 0
    current.attempt_count = 0
    current.error = None
    current.requires_attention = False
    await session.commit()

    try:
        enqueue_task(task_name, project_id)
    except Exception as error:
        current.status = "failed"
        current.requires_attention = True
        current.error = "任务入队失败，请重试"
        await session.commit()
        raise HTTPException(status_code=503, detail="任务入队失败，请稍后重试") from error
    return RetryResponse(project_id=project_id, stage=stage, status="pending")
