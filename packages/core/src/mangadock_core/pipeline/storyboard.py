import json
from importlib import resources

from mangadock_core.schemas import CharacterBible, Script, Storyboard
from mangadock_core.schemas.storyboard import validate_storyboard
from mangadock_providers import LLMProvider


async def generate_storyboard(
    script: Script,
    bible: CharacterBible,
    provider: LLMProvider,
) -> Storyboard:
    prompt = (
        resources.files("mangadock_core.pipeline")
        .joinpath("prompts", "storyboard_v1.md")
        .read_text(encoding="utf-8")
    )
    payload = {
        "script": script.model_dump(mode="json"),
        "character_bible": bible.model_dump(mode="json"),
    }
    board = await provider.chat(
        [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        Storyboard,
    )
    return validate_storyboard(board.model_dump(mode="json"), script, bible)
