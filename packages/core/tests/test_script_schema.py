import pytest
from pydantic import ValidationError

from mangadock_core.schemas import Script


def script_data() -> dict:
    return {
        "cast": [{"name": "林夏", "role": "调查记者", "weight": 1.0}],
        "episodes": [
            {
                "episode": 1,
                "estimated_duration_s": 999,
                "scenes": [
                    {
                        "index": 1,
                        "heading": "旧港仓库·夜·内景",
                        "action_beats": [
                            {"order": 1, "text": "林夏按下录音笔。"},
                            {"order": 3, "text": "周衡停在门口。"},
                        ],
                        "lines": [
                            {
                                "order": 2,
                                "character": "林夏",
                                "emotion": "震惊",
                                "text": "你以为删掉录音，就没有人知道真相了吗？",
                            },
                            {
                                "order": 4,
                                "character": "林夏",
                                "emotion": "坚定",
                                "text": "我只是在等你亲口承认。",
                            },
                        ],
                    }
                ],
            }
        ],
    }


def test_script_recomputes_duration_from_chinese_dialogue() -> None:
    script = Script.model_validate(script_data())

    assert script.episodes[0].estimated_duration_s == 6


def test_script_allows_action_only_scene_with_zero_duration() -> None:
    data = script_data()
    data["episodes"][0]["scenes"][0]["lines"] = []
    data["episodes"][0]["scenes"][0]["action_beats"] = [
        {"order": 1, "text": "仓库归于寂静。"}
    ]
    data["episodes"][0]["estimated_duration_s"] = -10

    script = Script.model_validate(data)

    assert script.episodes[0].estimated_duration_s == 0


def test_script_rejects_line_from_unknown_character() -> None:
    data = script_data()
    data["episodes"][0]["scenes"][0]["lines"][0]["character"] = "陌生人"
    with pytest.raises(ValidationError, match="cast"):
        Script.model_validate(data)


@pytest.mark.parametrize("first_order", [0, 2])
def test_scene_must_start_with_action_at_order_one(first_order: int) -> None:
    data = script_data()
    data["episodes"][0]["scenes"][0]["action_beats"][0]["order"] = first_order
    with pytest.raises(ValidationError):
        Script.model_validate(data)


def test_scene_rejects_non_alternating_content() -> None:
    data = script_data()
    data["episodes"][0]["scenes"][0]["action_beats"] = [
        {"order": 1, "text": "动作一"},
        {"order": 2, "text": "动作二"},
    ]
    data["episodes"][0]["scenes"][0]["lines"] = [
        {"order": 3, "character": "林夏", "emotion": "冷静", "text": "继续"},
        {"order": 4, "character": "林夏", "emotion": "冷静", "text": "调查"},
    ]
    with pytest.raises(ValidationError, match="alternate"):
        Script.model_validate(data)


def test_scene_rejects_gapped_order() -> None:
    data = script_data()
    data["episodes"][0]["scenes"][0]["lines"][1]["order"] = 5
    with pytest.raises(ValidationError):
        Script.model_validate(data)


def test_script_rejects_nonsequential_episodes_and_scenes() -> None:
    data = script_data()
    data["episodes"].append(deepcopy_episode(data["episodes"][0]))
    data["episodes"][1]["episode"] = 1
    with pytest.raises(ValidationError, match="sequential"):
        Script.model_validate(data)


def test_script_rejects_nonsequential_scene_indices() -> None:
    data = script_data()
    data["episodes"][0]["scenes"][0]["index"] = 2
    with pytest.raises(ValidationError, match="sequential"):
        Script.model_validate(data)


def deepcopy_episode(episode: dict) -> dict:
    import copy

    return copy.deepcopy(episode)


@pytest.mark.parametrize(
    ("container", "field"),
    [
        (("episodes", 0, "scenes", 0, "action_beats", 0), "text"),
        (("episodes", 0, "scenes", 0, "lines", 0), "emotion"),
        (("episodes", 0, "scenes", 0, "lines", 0), "text"),
        (("episodes", 0, "scenes", 0), "heading"),
    ],
)
def test_script_rejects_blank_text(container: tuple, field: str) -> None:
    data = script_data()
    target = data
    for key in container:
        target = target[key]
    target[field] = " "
    with pytest.raises(ValidationError):
        Script.model_validate(data)


def test_script_rejects_duplicate_cast_and_extra_fields() -> None:
    data = script_data()
    data["cast"].append({"name": "林夏", "role": "重复角色", "weight": 0.2})
    with pytest.raises(ValidationError, match="unique"):
        Script.model_validate(data)

    data = script_data()
    data["episodes"][0]["unexpected"] = True
    with pytest.raises(ValidationError):
        Script.model_validate(data)
