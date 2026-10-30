import pytest

from mangadock_core.pipeline import build_script, generate_episode, generate_outline
from mangadock_core.pipeline.characters import generate_character_bible
from mangadock_core.pipeline.storyboard import generate_storyboard
from mangadock_core.schemas import Chapter, Novel
from mangadock_providers import FakeLLMProvider


@pytest.mark.asyncio
async def test_character_and_storyboard_generation_uses_versioned_prompts() -> None:
    provider = FakeLLMProvider()
    novel = Novel(
        title="旧港",
        chapters=[Chapter(index=1, title="正文", text="内容")],
    )
    outline = await generate_outline(novel, provider)
    bible = await generate_character_bible(outline, provider)
    episodes = [await generate_episode(outline, number, provider) for number in (1, 2)]
    script = build_script(outline, episodes)

    board = await generate_storyboard(script, bible, provider)

    assert len(bible.characters) == 2
    assert len(board.episodes) == 2
    schema_names = [call["schema"].__name__ for call in provider.calls]
    assert "CharacterBible" in schema_names
    assert "Storyboard" in schema_names
    character_prompt = next(
        call for call in provider.calls if call["schema"].__name__ == "CharacterBible"
    )["messages"][0]["content"]
    storyboard_prompt = next(
        call for call in provider.calls if call["schema"].__name__ == "Storyboard"
    )["messages"][0]["content"]
    assert "5-8" in character_prompt
    assert "2、3、4 或 5 秒" in storyboard_prompt
    storyboard_user = next(
        call for call in provider.calls if call["schema"].__name__ == "Storyboard"
    )["messages"][1]["content"]
    assert "辫梢红绳" in storyboard_user
    assert "旧港" in storyboard_user
