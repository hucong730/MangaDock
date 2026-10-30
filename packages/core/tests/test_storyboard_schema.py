import pytest
from pydantic import ValidationError

from mangadock_core.schemas import (
    CharacterBible,
    Chapter,
    Episode,
    Line,
    Novel,
    Scene,
    Script,
)
from mangadock_core.schemas.storyboard import validate_storyboard


def character_bible() -> CharacterBible:
    return CharacterBible.model_validate(
        {
            "characters": [
                {
                    "name": "林夏",
                    "biography": "调查记者",
                    "prompt_zh": "林夏，辫梢红绳、藏青学生装",
                    "prompt_en": "Lin Xia, red ribbon braid, navy uniform",
                    "voice_prompt": "冷静女声",
                    "anchor_features": ["辫梢红绳", "藏青学生装", "齐肩短发", "琥珀眼睛", "银色录音笔"],
                },
                {
                    "name": "周衡",
                    "biography": "集团继承人",
                    "prompt_zh": "周衡，深灰西装、银框眼镜",
                    "prompt_en": "Zhou Heng, charcoal suit, silver glasses",
                    "voice_prompt": "低沉男声",
                    "anchor_features": ["深灰西装", "银框眼镜", "黑色短发", "银色袖扣", "冷峻眼神"],
                },
            ]
        }
    )


def script() -> Script:
    return Script.model_validate(
        {
            "cast": [{"name": "林夏", "role": "调查记者", "weight": 1}],
            "episodes": [
                {
                    "episode": 1,
                    "estimated_duration_s": 0,
                    "scenes": [
                        {
                            "index": 1,
                            "heading": "仓库·夜·内景",
                            "action_beats": [{"order": 1, "text": "林夏按下录音笔"}, {"order": 3, "text": "周衡停下"}],
                            "lines": [
                                {"order": 2, "character": "林夏", "emotion": "震惊", "text": "你在说谎"},
                                {"order": 4, "character": "林夏", "emotion": "坚定", "text": "我承认"},
                            ],
                        }
                    ],
                }
            ],
        }
    )


def storyboard_data() -> dict:
    return {
        "episodes": [
            {
                "episode": 1,
                "segments": [
                    {
                        "index": 1,
                        "duration_s": 0,
                        "cuts": [
                            {
                                "index": 1,
                                "duration_s": 3,
                                "characters": ["林夏", "周衡"],
                                "prompt": "<image1>林夏</image1><image2>周衡</image2>，林夏，辫梢红绳、藏青学生装；周衡，深灰西装、银框眼镜；仓库中近景",
                                "camera": "推近",
                                "line_refs": [{"scene": 1, "order": 2}],
                                "scene_ref": None,
                                "keyframe_image": None,
                            },
                            {
                                "index": 2,
                                "duration_s": 4,
                                "characters": ["林夏"],
                                "prompt": "<image1>林夏</image1>，林夏，藏青学生装；周衡停下，双人中景",
                                "camera": "后拉",
                                "line_refs": [{"scene": 1, "order": 4}],
                                "scene_ref": None,
                                "keyframe_image": {
                                    "path": "projects/1/images/cut.png",
                                    "width": 1024,
                                    "height": 768,
                                    "format": "png",
                                    "workflow_id": "storyboard_keyframe_v1",
                                },
                            },
                        ],
                    }
                ],
            }
        ]
    }


def test_storyboard_validates_full_script_coverage() -> None:
    board = validate_storyboard(
        storyboard_data(),
        script(),
        character_bible(),
    )

    assert board.episodes[0].segments[0].duration_s == 7
    assert board.episodes[0].segments[0].cuts[1].keyframe_image.width == 1024


@pytest.mark.parametrize("duration", [1, 6])
def test_cut_duration_hard_gate(duration: int) -> None:
    data = storyboard_data()
    data["episodes"][0]["segments"][0]["cuts"][0]["duration_s"] = duration
    with pytest.raises(ValidationError):
        validate_storyboard(data, script(), character_bible())


def test_segment_duration_must_not_exceed_fifteen_seconds() -> None:
    data = storyboard_data()
    data["episodes"][0]["segments"][0]["cuts"].append(
        {
            "index": 3,
            "duration_s": 5,
            "characters": ["林夏"],
            "prompt": "林夏，红绳",
            "camera": "固定",
            "line_refs": [],
            "scene_ref": None,
            "keyframe_image": None,
        }
    )
    data["episodes"][0]["segments"][0]["cuts"].append(
        {
            "index": 4,
            "duration_s": 5,
            "characters": ["林夏"],
            "prompt": "林夏，红绳",
            "camera": "固定",
            "line_refs": [],
            "scene_ref": None,
            "keyframe_image": None,
        }
    )
    with pytest.raises(ValidationError, match="15"):
        validate_storyboard(data, script(), character_bible())


def test_unknown_character_is_rejected() -> None:
    data = storyboard_data()
    data["episodes"][0]["segments"][0]["cuts"][0]["characters"] = ["陌生人"]
    with pytest.raises(ValueError, match="cast"):
        validate_storyboard(data, script(), character_bible())


def test_prompt_must_include_character_anchor() -> None:
    data = storyboard_data()
    data["episodes"][0]["segments"][0]["cuts"][0]["prompt"] = "仓库夜景"
    with pytest.raises(ValueError, match="anchor"):
        validate_storyboard(data, script(), character_bible())


@pytest.mark.parametrize("mode", ["missing", "reordered", "reused", "unknown"])
def test_line_refs_must_cover_each_line_once_in_order(mode: str) -> None:
    data = storyboard_data()
    cuts = data["episodes"][0]["segments"][0]["cuts"]
    if mode == "missing":
        cuts.pop(0)
    elif mode == "reordered":
        cuts.reverse()
    elif mode == "reused":
        cuts[1]["line_refs"] = [{"scene": 1, "order": 2}]
    else:
        cuts[0]["line_refs"] = [{"scene": 1, "order": 99}]
    if mode in {"missing", "reordered"}:
        for index, cut in enumerate(cuts, start=1):
            cut["index"] = index
    with pytest.raises(ValueError, match="line_refs"):
        validate_storyboard(data, script(), character_bible())


def test_scene_ref_must_be_null() -> None:
    data = storyboard_data()
    data["episodes"][0]["segments"][0]["cuts"][0]["scene_ref"] = "scene.png"
    with pytest.raises(ValidationError):
        validate_storyboard(data, script(), character_bible())


def test_cut_indices_must_be_sequential() -> None:
    data = storyboard_data()
    data["episodes"][0]["segments"][0]["cuts"][0]["index"] = 2
    with pytest.raises(ValidationError, match="sequential"):
        validate_storyboard(data, script(), character_bible())


def test_segment_indices_must_be_sequential() -> None:
    data = storyboard_data()
    data["episodes"][0]["segments"][0]["index"] = 2
    with pytest.raises(ValidationError, match="sequential"):
        validate_storyboard(data, script(), character_bible())


def test_storyboard_episode_numbers_must_be_sequential() -> None:
    data = storyboard_data()
    data["episodes"][0]["episode"] = 2
    with pytest.raises(ValidationError, match="sequential"):
        validate_storyboard(data, script(), character_bible())


def test_storyboard_must_cover_script_episodes() -> None:
    data = storyboard_data()
    data["episodes"].append({"episode": 2, "segments": data["episodes"][0]["segments"]})
    with pytest.raises(ValueError, match="every script episode"):
        validate_storyboard(data, script(), character_bible())


def test_line_ref_scene_must_exist() -> None:
    data = storyboard_data()
    data["episodes"][0]["segments"][0]["cuts"][0]["line_refs"] = [
        {"scene": 99, "order": 2}
    ]
    with pytest.raises(ValueError, match="line_refs"):
        validate_storyboard(data, script(), character_bible())


def test_characters_are_unique_and_limited_to_four() -> None:
    data = storyboard_data()
    data["episodes"][0]["segments"][0]["cuts"][0]["characters"] = ["林夏", "林夏"]
    with pytest.raises(ValueError, match="unique"):
        validate_storyboard(data, script(), character_bible())

    data["episodes"][0]["segments"][0]["cuts"][0]["characters"] = [
        "林夏",
        "周衡",
        "角色三",
        "角色四",
        "角色五",
    ]
    with pytest.raises(ValueError, match="4"):
        validate_storyboard(data, script(), character_bible())


def test_reference_tokens_must_match_character_order() -> None:
    data = storyboard_data()
    data["episodes"][0]["segments"][0]["cuts"][0]["prompt"] = (
        "<image2>周衡</image2><image1>林夏</image1>，林夏，辫梢红绳；周衡，深灰西装"
    )
    with pytest.raises(ValueError, match="image"):
        validate_storyboard(data, script(), character_bible())
