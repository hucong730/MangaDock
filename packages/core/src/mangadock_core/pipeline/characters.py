from importlib import resources

from mangadock_core.schemas import CharacterBible, Outline
from mangadock_core.schemas.character import validate_character_cast
from mangadock_providers import LLMProvider


async def generate_character_bible(
    outline: Outline,
    provider: LLMProvider,
) -> CharacterBible:
    prompt = (
        resources.files("mangadock_core.pipeline")
        .joinpath("prompts", "characters_v1.md")
        .read_text(encoding="utf-8")
    )
    bible = await provider.chat(
        [
            {"role": "system", "content": prompt},
            {"role": "user", "content": outline.model_dump_json()},
        ],
        CharacterBible,
    )
    validate_character_cast(bible, outline.cast)
    return bible
