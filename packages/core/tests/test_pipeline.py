import pytest

from mangadock_core.pipeline import build_script, generate_episode, generate_outline
from mangadock_core.schemas import Chapter, Novel
from mangadock_providers import FakeLLMProvider


@pytest.mark.asyncio
async def test_fake_provider_runs_complete_generation_flow() -> None:
    novel = Novel(
        title="旧港",
        chapters=[Chapter(index=1, title="第一章 归来", text="林夏回到旧港。")],
    )
    provider = FakeLLMProvider()

    outline = await generate_outline(novel, provider)
    episodes = [
        await generate_episode(outline, episode, provider)
        for episode in (2, 1)
    ]
    script = build_script(outline, episodes)

    assert len(outline.episode_beat) == 2
    assert [episode.episode for episode in script.episodes] == [1, 2]
    assert script.cast == outline.cast
    assert script.episodes[0].estimated_duration_s >= 0
    first_call = provider.calls[0]
    assert first_call["messages"][0]["role"] == "system"
    assert "抽核" in first_call["messages"][0]["content"]
    assert "大爆点" in first_call["messages"][0]["content"]
    assert "旧港" in first_call["messages"][1]["content"]
    episode_call = provider.calls[1]
    assert "严格交替" in episode_call["messages"][0]["content"]
    assert '"episode": 2' in episode_call["messages"][1]["content"]


@pytest.mark.asyncio
async def test_generate_episode_rejects_missing_episode_beat() -> None:
    novel = Novel(
        title="旧港",
        chapters=[Chapter(index=1, title="正文", text="内容")],
    )
    provider = FakeLLMProvider()
    outline = await generate_outline(novel, provider)

    with pytest.raises(ValueError, match="Episode 99"):
        await generate_episode(outline, 99, provider)
