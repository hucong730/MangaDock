import pytest
from pydantic import BaseModel

from mangadock_core.schemas import CharacterBible, Storyboard
from mangadock_providers import FakeLLMProvider


class CastMember(BaseModel):
    name: str
    role: str
    weight: float


class EpisodeBeat(BaseModel):
    episode: int
    summary: str
    payoff_type: str
    payoff_intensity: int


class Outline(BaseModel):
    synopsis: str
    cast: list[CastMember]
    episode_beat: list[EpisodeBeat]
    asset_list: list[str]


class ActionBeat(BaseModel):
    order: int
    text: str


class Line(BaseModel):
    order: int
    character: str
    emotion: str
    text: str


class Scene(BaseModel):
    index: int
    heading: str
    action_beats: list[ActionBeat]
    lines: list[Line]


class Episode(BaseModel):
    episode: int
    estimated_duration_s: int
    scenes: list[Scene]


@pytest.mark.asyncio
async def test_fake_provider_returns_supported_models() -> None:
    provider = FakeLLMProvider()

    outline = await provider.chat([], Outline)
    episode = await provider.chat(
        [{"role": "user", "content": '{"episode": 2}'}],
        Episode,
    )

    assert len(outline.episode_beat) == 2
    assert episode.episode == 2
    assert episode.scenes[0].lines[0].character == "林夏"


@pytest.mark.asyncio
async def test_fake_provider_rejects_unknown_schema() -> None:
    class Unsupported(BaseModel):
        value: str

    with pytest.raises(ValueError, match="Unsupported"):
        await FakeLLMProvider().chat([], Unsupported)


@pytest.mark.asyncio
async def test_fake_provider_returns_character_bible_and_storyboard() -> None:
    provider = FakeLLMProvider()

    bible = await provider.chat([], CharacterBible)
    board = await provider.chat([], Storyboard)

    assert len(bible.characters) == 2
    assert len(board.episodes) == 2
    assert board.episodes[0].segments[0].cuts[0].keyframe_image is None
