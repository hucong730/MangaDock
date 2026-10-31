from unittest.mock import Mock

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from mangadock_api.models import (
    ProjectAssetRecord,
    ProjectRecord,
    ProjectStageRecord,
    ProjectVideoRouteRecord,
)
from mangadock_api.routers import media
from test_projects import create_provider


async def create_media_project(session_factory, provider_id: int, suffix="a"):
    async with session_factory() as session:
        project = ProjectRecord(
            title=f"项目{suffix}",
            source_filename="novel.txt",
            source_media_type="text/plain",
            provider_id=provider_id,
            novel_json={"title": "项目", "chapters": []},
            script_json={"episodes": []},
        )
        session.add(project)
        await session.flush()
        session.add(
            ProjectAssetRecord(
                project_id=project.id,
                kind="storyboard",
                payload_json={
                    "episodes": [{
                        "episode": 1,
                        "segments": [{
                            "index": 1,
                            "duration_s": 7,
                            "cuts": [
                                {
                                    "index": 1,
                                    "duration_s": 3,
                                    "characters": ["林夏"],
                                    "prompt": "<image1>林夏</image1>林夏，红绳",
                                    "camera": "推近",
                                    "line_refs": [{"scene": 1, "order": 2}],
                                    "scene_ref": None,
                                    "keyframe_image": {
                                        "path": "frame-1.png",
                                        "width": 1024,
                                        "height": 1024,
                                        "format": "png",
                                        "workflow_id": "storyboard_keyframe_v1",
                                    },
                                },
                                {
                                    "index": 2,
                                    "duration_s": 4,
                                    "characters": ["林夏"],
                                    "prompt": "<image1>林夏</image1>林夏，红绳",
                                    "camera": "后拉",
                                    "line_refs": [{"scene": 1, "order": 4}],
                                    "scene_ref": None,
                                    "keyframe_image": {
                                        "path": "frame-2.png",
                                        "width": 1024,
                                        "height": 1024,
                                        "format": "png",
                                        "workflow_id": "storyboard_keyframe_v1",
                                    },
                                },
                            ],
                        }],
                    }]
                },
            )
        )
        session.add(
            ProjectAssetRecord(
                project_id=project.id,
                kind="dubbing",
                payload_json={
                    "episodes": [{
                        "episode": 1,
                        "source_fingerprint": "voice-v1",
                        "lines": [],
                    }]
                },
            )
        )
        session.add_all(
            [
                ProjectStageRecord(project_id=project.id, stage="dubbing", status="done"),
                ProjectStageRecord(project_id=project.id, stage="render", status="pending"),
                ProjectStageRecord(project_id=project.id, stage="compose", status="pending"),
            ]
        )
        await session.commit()
        return project


async def create_video_provider(client: AsyncClient) -> int:
    response = await client.post(
        "/api/v1/video-providers/",
        json={
            "name": "mock-wan",
            "kind": "wan",
            "base_url": "http://localhost:8188",
            "model": "wan2.2",
            "api_key_env": "COMFYUI_API_KEY",
            "config_json": {},
        },
    )
    return response.json()["id"]


@pytest.mark.asyncio
async def test_render_persists_routes_and_rejects_active_duplicate(
    client: AsyncClient,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm_id = await create_provider(client)
    video_id = await create_video_provider(client)
    project = await create_media_project(session_factory, llm_id)
    queue = Mock()
    monkeypatch.setattr(media, "enqueue_task", queue)

    response = await client.post(
        f"/api/v1/projects/{project.id}/episodes/1/render",
        json={"video_provider_id": video_id, "segment_providers": {"1": video_id}},
    )

    assert response.status_code == 202
    queue.assert_called_once_with("mangadock_worker.tasks.stage_dubbing", project.id, 1)
    async with session_factory() as session:
        routes = list((await session.scalars(select(ProjectVideoRouteRecord))).all())
    assert {(route.episode, route.segment_index) for route in routes} == {(0, 0), (1, 1)}

    duplicate = await client.post(
        f"/api/v1/projects/{project.id}/episodes/1/render",
        json={"video_provider_id": video_id},
    )
    assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_completed_pending_assets_do_not_block_render(
    client: AsyncClient,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm_id = await create_provider(client)
    project = await create_media_project(session_factory, llm_id)
    async with session_factory() as session:
        session.add(
            ProjectAssetRecord(
                project_id=project.id,
                kind="render",
                payload_json={
                    "episodes": [{
                        "episode": 1,
                        "segments": [{
                            "index": 1,
                            "cuts": [{
                                "index": 1,
                                "duration_s": 3,
                                "status": "done",
                                "attempt_count": 1,
                                "provider_id": None,
                                "clip_path": "clip.mp4",
                                "source_fingerprint": "a",
                            }],
                        }],
                    }]
                },
            )
        )
        await session.commit()
    monkeypatch.setattr(media, "enqueue_task", Mock())

    response = await client.post(
        f"/api/v1/projects/{project.id}/episodes/1/render",
        json={},
    )

    assert response.status_code == 202


@pytest.mark.asyncio
async def test_render_requires_storyboard(client: AsyncClient, session_factory) -> None:
    llm_id = await create_provider(client)
    async with session_factory() as session:
        project = ProjectRecord(
            title="无分镜",
            source_filename="novel.txt",
            source_media_type="text/plain",
            provider_id=llm_id,
            novel_json={"title": "无分镜", "chapters": []},
        )
        session.add(project)
        await session.commit()
        project_id = project.id

    response = await client.post(f"/api/v1/projects/{project_id}/episodes/1/render", json={})

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_render_progress_cut_retry_and_export(client: AsyncClient, session_factory, monkeypatch) -> None:
    llm_id = await create_provider(client)
    project = await create_media_project(session_factory, llm_id)
    async with session_factory() as session:
        session.add(
            ProjectAssetRecord(
                project_id=project.id,
                kind="render",
                payload_json={
                    "episodes": [{
                        "episode": 1,
                        "segments": [{
                            "index": 1,
                            "cuts": [
                                {"index": 1, "duration_s": 3, "status": "done", "attempt_count": 1, "provider_id": None, "clip_path": "clip-1.mp4", "source_fingerprint": "a", "error": None},
                                {"index": 2, "duration_s": 4, "status": "failed", "attempt_count": 2, "provider_id": None, "clip_path": None, "source_fingerprint": "b", "error": "生成失败"},
                            ],
                        }],
                    }]
                },
            )
        )
        render = await session.scalar(
            select(ProjectStageRecord).where(
                ProjectStageRecord.project_id == project.id,
                ProjectStageRecord.stage == "render",
            )
        )
        render.status = "failed"
        session.add(
            ProjectAssetRecord(
                project_id=project.id,
                kind="compose",
                payload_json={
                    "episodes": [{
                        "episode": 1,
                        "status": "done",
                        "burned_path": "exports/episode_1.mp4",
                        "clean_path": "exports/episode_1_clean.mp4",
                        "srt_path": "exports/episode_1.srt",
                        "vtt_path": "exports/episode_1.vtt",
                        "duration_s": 7,
                        "width": 1920,
                        "height": 1080,
                        "source_fingerprint": "c",
                    }]
                },
            )
        )
        await session.commit()
    queue = Mock()
    monkeypatch.setattr(media, "enqueue_task", queue)

    progress = await client.get(f"/api/v1/projects/{project.id}/episodes/1/render")
    assert progress.status_code == 200
    assert progress.json()["completed_cuts"] == 1
    assert progress.json()["total_cuts"] == 2
    retry = await client.post(
        f"/api/v1/projects/{project.id}/episodes/1/segments/1/cuts/2/retry"
    )
    assert retry.status_code == 202
    queue.assert_called_once_with("mangadock_worker.tasks.retry_render_cut", project.id, 1, 1, 2)
    running_retry = await client.post(
        f"/api/v1/projects/{project.id}/episodes/1/segments/1/cuts/1/retry"
    )
    assert running_retry.status_code == 409

    export = await client.get(f"/api/v1/projects/{project.id}/episodes/1/export")
    assert export.status_code == 200
    assert export.json()["clean_path"] == "exports/episode_1_clean.mp4"


@pytest.mark.asyncio
async def test_cut_retry_checks_project_ownership(client: AsyncClient, session_factory) -> None:
    llm_id = await create_provider(client)
    first = await create_media_project(session_factory, llm_id, "a")
    second = await create_media_project(session_factory, llm_id, "b")

    response = await client.post(
        f"/api/v1/projects/{first.id}/episodes/1/segments/1/cuts/1/retry"
    )

    assert response.status_code == 404
    assert second.id != first.id
