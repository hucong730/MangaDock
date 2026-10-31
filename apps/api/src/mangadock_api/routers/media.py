from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mangadock_api.database import get_db
from mangadock_api.media_schemas import RenderRequest, RenderStartResponse
from mangadock_api.models import (
    ProjectAssetRecord,
    ProjectStageRecord,
    ProjectVideoRouteRecord,
    VideoProviderRecord,
)
from mangadock_api.queue import enqueue_task
from mangadock_api.routers.projects import get_project

router = APIRouter(prefix="/api/v1/projects", tags=["media"])


async def get_asset(session: AsyncSession, project_id: int, kind: str):
    return await session.scalar(
        select(ProjectAssetRecord).where(
            ProjectAssetRecord.project_id == project_id,
            ProjectAssetRecord.kind == kind,
        )
    )


async def get_stage(session: AsyncSession, project_id: int, name: str):
    stage = await session.scalar(
        select(ProjectStageRecord).where(
            ProjectStageRecord.project_id == project_id,
            ProjectStageRecord.stage == name,
        )
    )
    if stage is None:
        stage = ProjectStageRecord(project_id=project_id, stage=name)
        session.add(stage)
        await session.flush()
    return stage


def reset_stage(stage, status="pending") -> None:
    stage.status = status
    stage.completed_items = 0
    stage.attempt_count = 0
    stage.error = None
    stage.requires_attention = False


def asset_in_flight(asset, kind: str, episode: int) -> bool:
    if asset is None:
        return False
    episode_asset = next(
        (item for item in asset.payload_json["episodes"] if item["episode"] == episode),
        None,
    )
    if episode_asset is None:
        return False
    if kind == "compose":
        return episode_asset["status"] in {"pending", "running"}
    if kind == "dubbing":
        return any(
            line["status"] in {"pending", "running"}
            for line in episode_asset["lines"]
        )
    return any(
        cut["status"] in {"pending", "running"}
        for segment in episode_asset["segments"]
        for cut in segment["cuts"]
    )


async def save_route(
    session: AsyncSession,
    project_id: int,
    episode: int,
    segment: int,
    provider_id: int,
) -> None:
    provider = await session.get(VideoProviderRecord, provider_id, with_for_update=True)
    if provider is None:
        raise HTTPException(status_code=404, detail="视频 Provider 不存在")
    if not provider.enabled:
        raise HTTPException(status_code=409, detail="视频 Provider 已停用")
    route = await session.scalar(
        select(ProjectVideoRouteRecord).where(
            ProjectVideoRouteRecord.project_id == project_id,
            ProjectVideoRouteRecord.episode == episode,
            ProjectVideoRouteRecord.segment_index == segment,
        )
    )
    if route is None:
        route = ProjectVideoRouteRecord(
            project_id=project_id,
            episode=episode,
            segment_index=segment,
            video_provider_id=provider_id,
        )
        session.add(route)
    else:
        route.video_provider_id = provider_id


@router.post("/{project_id}/episodes/{episode}/render", response_model=RenderStartResponse, status_code=202)
async def start_render(
    project_id: int,
    episode: int,
    payload: RenderRequest,
    session: AsyncSession = Depends(get_db),
) -> RenderStartResponse:
    await get_project(session, project_id)
    storyboard = await get_asset(session, project_id, "storyboard")
    if storyboard is None:
        raise HTTPException(status_code=409, detail="Storyboard 尚未生成")
    board_episode = next(
        (item for item in storyboard.payload_json["episodes"] if item["episode"] == episode),
        None,
    )
    if board_episode is None:
        raise HTTPException(status_code=404, detail="剧集不存在")
    if any(
        cut["keyframe_image"] is None
        for segment in board_episode["segments"]
        for cut in segment["cuts"]
    ):
        raise HTTPException(status_code=409, detail="关键帧尚未生成完整")
    for name in ("dubbing", "render", "compose"):
        stage = await get_stage(session, project_id, name)
        asset = await get_asset(session, project_id, name)
        if stage.status == "running" or (
            stage.status == "pending" and asset_in_flight(asset, name, episode)
        ):
            raise HTTPException(status_code=409, detail="当前项目已有渲染任务进行中")
    if payload.video_provider_id is not None:
        await save_route(session, project_id, 0, 0, payload.video_provider_id)
    valid_segments = {segment["index"] for segment in board_episode["segments"]}
    for raw_segment, provider_id in payload.segment_providers.items():
        try:
            segment = int(raw_segment)
        except ValueError as error:
            raise HTTPException(status_code=422, detail="分镜段编号无效") from error
        if segment not in valid_segments:
            raise HTTPException(status_code=404, detail="分镜段不存在")
        await save_route(session, project_id, episode, segment, provider_id)

    dubbing_asset = await get_asset(session, project_id, "dubbing")
    dubbing_episode = None
    if dubbing_asset is not None:
        dubbing_episode = next(
            (item for item in dubbing_asset.payload_json["episodes"] if item["episode"] == episode),
            None,
        )
    dubbing_ready = dubbing_episode is not None and all(
        line["status"] == "done" for line in dubbing_episode["lines"]
    )
    dubbing_stage = await get_stage(session, project_id, "dubbing")
    render_stage = await get_stage(session, project_id, "render")
    compose_stage = await get_stage(session, project_id, "compose")
    if not dubbing_ready:
        reset_stage(dubbing_stage)
    reset_stage(render_stage)
    reset_stage(compose_stage)
    await session.commit()
    task = (
        "mangadock_worker.tasks.start_render"
        if dubbing_ready
        else "mangadock_worker.tasks.stage_dubbing"
    )
    try:
        enqueue_task(task, project_id, episode)
    except Exception as error:
        render_stage.status = "failed"
        render_stage.requires_attention = True
        render_stage.error = "任务入队失败，请重试"
        await session.commit()
        raise HTTPException(status_code=503, detail="任务入队失败，请稍后重试") from error
    return RenderStartResponse(project_id=project_id, episode=episode, status="pending")


@router.get("/{project_id}/episodes/{episode}/render")
async def render_progress(
    project_id: int,
    episode: int,
    session: AsyncSession = Depends(get_db),
) -> dict:
    await get_project(session, project_id)
    asset = await get_asset(session, project_id, "render")
    if asset is None:
        raise HTTPException(status_code=404, detail="渲染尚未开始")
    episode_asset = next(
        (item for item in asset.payload_json["episodes"] if item["episode"] == episode),
        None,
    )
    if episode_asset is None:
        raise HTTPException(status_code=404, detail="剧集渲染不存在")
    cuts = [cut for segment in episode_asset["segments"] for cut in segment["cuts"]]
    segments = []
    for segment in episode_asset["segments"]:
        completed = sum(cut["status"] == "done" for cut in segment["cuts"])
        failed = any(cut["status"] in {"failed", "outdated"} for cut in segment["cuts"])
        segments.append(
            {
                **segment,
                "status": "failed" if failed else "done" if completed == len(segment["cuts"]) else "running",
                "completed_cuts": completed,
                "total_cuts": len(segment["cuts"]),
            }
        )
    stage = await get_stage(session, project_id, "render")
    return {
        "project_id": project_id,
        "episode": episode,
        "status": stage.status,
        "error": stage.error,
        "completed_cuts": sum(cut["status"] == "done" for cut in cuts),
        "total_cuts": len(cuts),
        "segments": segments,
    }


@router.post("/{project_id}/episodes/{episode}/segments/{segment}/cuts/{cut}/retry", status_code=202)
async def retry_cut(
    project_id: int,
    episode: int,
    segment: int,
    cut: int,
    session: AsyncSession = Depends(get_db),
) -> dict:
    await get_project(session, project_id)
    stage = await get_stage(session, project_id, "render")
    if stage.status == "running":
        raise HTTPException(status_code=409, detail="渲染进行中，不能重试单镜")
    asset = await get_asset(session, project_id, "render")
    if asset is None:
        raise HTTPException(status_code=404, detail="渲染尚未开始")
    try:
        clip = next(
            cut_asset
            for episode_asset in asset.payload_json["episodes"]
            if episode_asset["episode"] == episode
            for segment_asset in episode_asset["segments"]
            if segment_asset["index"] == segment
            for cut_asset in segment_asset["cuts"]
            if cut_asset["index"] == cut
        )
    except StopIteration as error:
        raise HTTPException(status_code=404, detail="镜头不存在") from error
    if clip["status"] != "failed":
        raise HTTPException(status_code=409, detail="仅失败镜头可以重试")
    clip["status"] = "pending"
    clip["attempt_count"] = 0
    clip["error"] = None
    stage.status = "pending"
    stage.error = None
    stage.requires_attention = False
    await session.commit()
    try:
        enqueue_task("mangadock_worker.tasks.retry_render_cut", project_id, episode, segment, cut)
    except Exception as error:
        raise HTTPException(status_code=503, detail="任务入队失败，请稍后重试") from error
    return {"status": "pending", "episode": episode, "segment": segment, "cut": cut}


@router.get("/{project_id}/episodes/{episode}/export")
async def episode_export(
    project_id: int,
    episode: int,
    session: AsyncSession = Depends(get_db),
) -> dict:
    await get_project(session, project_id)
    asset = await get_asset(session, project_id, "compose")
    if asset is None:
        raise HTTPException(status_code=404, detail="成片尚未合成")
    export = next(
        (item for item in asset.payload_json["episodes"] if item["episode"] == episode),
        None,
    )
    if export is None:
        raise HTTPException(status_code=404, detail="成片尚未合成")
    return export
