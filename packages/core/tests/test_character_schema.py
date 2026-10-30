import pytest
from pydantic import ValidationError

from mangadock_core.schemas import CharacterBible, CastMember
from mangadock_core.schemas.character import validate_character_cast


def spec(name: str = "林夏") -> dict:
    return {
        "name": name,
        "biography": "调查记者，十年前事故的幸存者。",
        "prompt_zh": "林夏，辫梢红绳、藏青学生装，正面全身。",
        "prompt_en": "Lin Xia, red ribbon braid, navy school uniform, full body",
        "voice_prompt": "冷静克制的年轻女声，语速中等。",
        "anchor_features": ["辫梢红绳", "藏青学生装", "齐肩短发", "琥珀色眼睛", "银色录音笔"],
    }


def test_character_bible_accepts_valid_cast() -> None:
    bible = CharacterBible.model_validate({"characters": [spec()]})

    validate_character_cast(
        bible,
        [CastMember(name="林夏", role="调查记者", weight=1.0)],
    )
    assert bible.characters[0].anchor_features[0] == "辫梢红绳"


@pytest.mark.parametrize(
    "features",
    [
        ["仅一项", "两项", "三项", "四项"],
        ["一", "二", "三", "四", "五", "六", "七", "八", "九"],
        ["红绳", "红绳", "学生装", "短发", "眼睛"],
    ],
)
def test_character_rejects_invalid_anchor_features(features: list[str]) -> None:
    value = spec()
    value["anchor_features"] = features
    with pytest.raises(ValidationError):
        CharacterBible.model_validate({"characters": [value]})


def test_character_rejects_blank_anchor_feature() -> None:
    value = spec()
    value["anchor_features"][0] = " "
    with pytest.raises(ValidationError):
        CharacterBible.model_validate({"characters": [value]})


def test_character_cast_must_match_exactly() -> None:
    bible = CharacterBible.model_validate({"characters": [spec()]})
    with pytest.raises(ValueError, match="cast"):
        validate_character_cast(
            bible,
            [CastMember(name="周衡", role="继承人", weight=1.0)],
        )


def test_character_rejects_blank_prompt_and_extra_field() -> None:
    value = spec()
    value["prompt_en"] = " "
    with pytest.raises(ValidationError):
        CharacterBible.model_validate({"characters": [value]})

    value = spec()
    value["unexpected"] = True
    with pytest.raises(ValidationError):
        CharacterBible.model_validate({"characters": [value]})
