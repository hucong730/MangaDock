from pydantic import Field, field_validator

from mangadock_core.schemas.base import SchemaModel
from mangadock_core.schemas.outline import CastMember


class CharacterSpec(SchemaModel):
    name: str = Field(min_length=1)
    biography: str = Field(min_length=1)
    prompt_zh: str = Field(min_length=1)
    prompt_en: str = Field(min_length=1)
    voice_prompt: str = Field(min_length=1)
    anchor_features: list[str] = Field(min_length=5, max_length=8)

    @field_validator("anchor_features")
    @classmethod
    def validate_anchor_features(cls, value: list[str]) -> list[str]:
        if any(not feature for feature in value):
            raise ValueError("Anchor features must not be blank")
        if len(value) != len(set(value)):
            raise ValueError("Anchor features must be unique")
        return value


class CharacterBible(SchemaModel):
    characters: list[CharacterSpec] = Field(min_length=1)


def validate_character_cast(
    bible: CharacterBible,
    cast: list[CastMember],
) -> None:
    character_names = [character.name for character in bible.characters]
    cast_names = [member.name for member in cast]
    if len(character_names) != len(cast_names) or set(character_names) != set(cast_names):
        raise ValueError("Character bible must cover the exact cast")
