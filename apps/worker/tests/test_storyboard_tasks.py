import pytest
from sqlalchemy import select

from mangadock_persistence.models import (
    CharacterImageRecord,
    CharacterRecord,
    ProjectAssetRecord,
    ProjectProviderRouteRecord,
    ProjectStageRecord,
)
from mangadock_providers import FakeLLMProvider, ImageProviderAPIError, MockImageProvider
from mangadock_worker import character_tasks, storyboard_tasks
from mangadock_worker.character_tasks import confirm_character_anchor, run_character_stage
from mangadock_worker.storyboard_tasks import run_storyboard_stage
from test_character_tasks import project_factory


@pytest.fixture(autouse=True)
def isolate_providers(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        storyboard_tasks,
        "image_provider_for_record",
        lambda record, workflow_id, output_dir: MockImageProvider(
            output_dir=output_dir,
            workflow_id=workflow_id,
        ),
    )
    monkeypatch.setattr(
        storyboard_tasks,
        "provider_for_record",
        lambda _: FakeLLMProvider(),
    )


class InvalidStoryboardProvider(FakeLLMProvider):
    def __init__(self, mode: str) -> None:
        super().__init__()
        self.mode = mode
        self.failed = False

    async def chat(self, messages, schema):
        if schema.__name__ == "Storyboard" and not self.failed:
            self.failed = True
            board = await super().chat(messages, schema)
            cut = board.episodes[0].segments[0].cuts[0]
            if self.mode == "duration":
                cut.duration_s = 6
            elif self.mode == "character":
                cut.characters = ["陌生人"]
            elif self.mode == "anchor":
                cut.prompt = "旧港仓库，没有角色特征"
            elif self.mode == "coverage":
                cut.line_refs = []
            return board
        return await super().chat(messages, schema)


class FailingOnceImageProvider(MockImageProvider):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.failed = False
        self.references = []

    async def generate(self, prompt, reference_images, size):
        self.references.append(reference_images)
        if not self.failed:
            self.failed = True
            raise ImageProviderAPIError("keyframe failed")
        return await super().generate(prompt, reference_images, size)


async def complete_characters(project_id: int, session_factory) -> None:
    assert await run_character_stage(project_id)
    async with session_factory() as session:
        characters = list(
            (
                await session.scalars(
                    select(CharacterRecord).where(CharacterRecord.project_id == project_id)
                )
            ).all()
        )
    for character in characters:
        await confirm_character_anchor(character.id)


@pytest.mark.asyncio
async def test_storyboard_generates_valid_json_and_keyframes(
    project_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_project, session_factory = project_factory
    project_id = await create_project()
    await complete_characters(project_id, session_factory)
    image_providers = []

    def image_factory(record, workflow_id, output_dir):
        provider = FailingOnceImageProvider(
            output_dir=output_dir,
            workflow_id=workflow_id,
        )
        provider.failed = True
        image_providers.append(provider)
        return provider

    monkeypatch.setattr(storyboard_tasks, "image_provider_for_record", image_factory)

    assert await run_storyboard_stage(project_id) is True

    async with session_factory() as session:
        asset = await session.scalar(
            select(ProjectAssetRecord).where(
                ProjectAssetRecord.project_id == project_id,
                ProjectAssetRecord.kind == "storyboard",
            )
        )
        stage = await session.scalar(
            select(ProjectStageRecord).where(
                ProjectStageRecord.project_id == project_id,
                ProjectStageRecord.stage == "storyboard",
            )
        )
    assert stage.status == "done"
    assert len(asset.payload_json["episodes"]) == 2
    first_cut = asset.payload_json["episodes"][0]["segments"][0]["cuts"][0]
    assert first_cut["duration_s"] in {2, 3, 4, 5}
    assert first_cut["scene_ref"] is None
    assert first_cut["keyframe_image"]["path"].startswith(
        f"projects/{project_id}/images/storyboard/"
    )
    assert not first_cut["keyframe_image"]["path"].startswith("/")
    assert len(image_providers[0].references[0]) == 2


@pytest.mark.asyncio
async def test_fake_mode_works_without_image_route(project_factory) -> None:
    create_project, session_factory = project_factory
    project_id = await create_project()
    async with session_factory() as session:
        route = await session.scalar(
            select(ProjectProviderRouteRecord).where(
                ProjectProviderRouteRecord.project_id == project_id,
                ProjectProviderRouteRecord.role == "image",
            )
        )
        await session.delete(route)
        await session.commit()

    await complete_characters(project_id, session_factory)

    assert await run_storyboard_stage(project_id) is True


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["duration", "character", "anchor", "coverage"])
async def test_invalid_storyboard_is_retried_once(project_factory, mode: str) -> None:
    create_project, session_factory = project_factory
    project_id = await create_project()
    await complete_characters(project_id, session_factory)
    provider = InvalidStoryboardProvider(mode)
    storyboard_tasks.provider_for_record = lambda _: provider

    assert await run_storyboard_stage(project_id) is True

    storyboard_calls = [call for call in provider.calls if call["schema"].__name__ == "Storyboard"]
    assert len(storyboard_calls) == 2
    async with session_factory() as session:
        stage = await session.scalar(
            select(ProjectStageRecord).where(
                ProjectStageRecord.project_id == project_id,
                ProjectStageRecord.stage == "storyboard",
            )
        )
    assert stage.status == "done"
    assert stage.attempt_count == 2


@pytest.mark.asyncio
async def test_failed_keyframe_retries_without_regenerating_llm(
    project_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_project, session_factory = project_factory
    project_id = await create_project()
    await complete_characters(project_id, session_factory)
    image_provider = None

    def failing_factory(record, workflow_id, output_dir):
        nonlocal image_provider
        if image_provider is None:
            image_provider = FailingOnceImageProvider(
                output_dir=output_dir,
                workflow_id=workflow_id,
            )
        return image_provider

    monkeypatch.setattr(storyboard_tasks, "image_provider_for_record", failing_factory)
    llm = FakeLLMProvider()
    monkeypatch.setattr(storyboard_tasks, "provider_for_record", lambda _: llm)

    assert await run_storyboard_stage(project_id) is False

    storyboard_tasks.image_provider_for_record = (
        lambda record, workflow_id, output_dir: MockImageProvider(
            output_dir=output_dir,
            workflow_id=workflow_id,
        )
    )
    assert await run_storyboard_stage(project_id) is True
    storyboard_calls = [call for call in llm.calls if call["schema"].__name__ == "Storyboard"]
    assert len(storyboard_calls) == 1
