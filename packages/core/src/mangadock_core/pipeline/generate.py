import json
from collections.abc import Sequence
from importlib import resources

from mangadock_core.schemas import Episode, Novel, Outline, Script
from mangadock_providers import LLMProvider


def load_prompt(filename: str) -> str:
    return (
        resources.files("mangadock_core.pipeline")
        .joinpath("prompts", filename)
        .read_text(encoding="utf-8")
    )


async def generate_outline(novel: Novel, provider: LLMProvider) -> Outline:
    messages = [
        {"role": "system", "content": load_prompt("outline_v1.md")},
        {"role": "user", "content": novel.model_dump_json()},
    ]
    return await provider.chat(messages, Outline)


async def generate_episode(
    outline: Outline,
    episode: int,
    provider: LLMProvider,
) -> Episode:
    if episode not in {beat.episode for beat in outline.episode_beat}:
        raise ValueError(f"Episode {episode} is not present in outline")
    payload = {"outline": outline.model_dump(mode="json"), "episode": episode}
    messages = [
        {"role": "system", "content": load_prompt("script_v1.md")},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    return await provider.chat(messages, Episode)


def build_script(outline: Outline, episodes: Sequence[Episode]) -> Script:
    return Script(
        cast=outline.cast,
        episodes=sorted(episodes, key=lambda episode: episode.episode),
    )
