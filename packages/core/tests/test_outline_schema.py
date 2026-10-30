from copy import deepcopy

import pytest
from pydantic import ValidationError

from mangadock_core.schemas import CastMember, Outline


def outline_data() -> dict:
    return {
        "synopsis": "调查记者林夏揭开旧港事故真相。",
        "cast": [
            {"name": "林夏", "role": "调查记者", "weight": 0.7},
            {"name": "周衡", "role": "集团继承人", "weight": 0.3},
        ],
        "episode_beat": [
            {
                "episode": 1,
                "summary": "林夏收到录音笔。",
                "payoff_type": "悬念钩子",
                "payoff_intensity": 3,
            },
            {
                "episode": 2,
                "summary": "周衡承认伪造证词。",
                "payoff_type": "身份反转",
                "payoff_intensity": 5,
            },
        ],
        "asset_list": ["旧港仓库", "银色录音笔"],
    }


def test_outline_accepts_approved_shape() -> None:
    outline = Outline.model_validate(outline_data())

    assert outline.cast[0] == CastMember(name="林夏", role="调查记者", weight=0.7)
    assert outline.episode_beat[1].payoff_intensity == 5


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("synopsis",), " "),
        (("cast",), []),
        (("cast", 0, "name"), ""),
        (("cast", 0, "role"), ""),
        (("cast", 0, "weight"), -0.1),
        (("cast", 0, "weight"), 1.1),
        (("episode_beat",), []),
        (("episode_beat", 0, "summary"), ""),
        (("episode_beat", 0, "payoff_type"), ""),
        (("episode_beat", 0, "payoff_intensity"), 0),
        (("episode_beat", 0, "payoff_intensity"), 6),
        (("asset_list", 0), ""),
    ],
)
def test_outline_rejects_invalid_fields(path: tuple, value: object) -> None:
    data = outline_data()
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(ValidationError):
        Outline.model_validate(data)


def test_outline_rejects_duplicate_cast_names() -> None:
    data = outline_data()
    data["cast"][1]["name"] = "林夏"
    with pytest.raises(ValidationError, match="unique"):
        Outline.model_validate(data)


def test_outline_rejects_nonsequential_episodes() -> None:
    data = outline_data()
    data["episode_beat"][1]["episode"] = 3
    with pytest.raises(ValidationError, match="sequential"):
        Outline.model_validate(data)


def test_outline_rejects_major_payoff_gap_over_eight() -> None:
    data = outline_data()
    data["episode_beat"][0]["payoff_intensity"] = 5
    data["episode_beat"][1]["payoff_intensity"] = 2
    data["episode_beat"].extend(
        {
            "episode": episode,
            "summary": "过渡。",
            "payoff_type": "危机升级",
            "payoff_intensity": 2,
        }
        for episode in range(3, 10)
    )
    data["episode_beat"].append(
        {
            "episode": 10,
            "summary": "迟到的爆点。",
            "payoff_type": "身份反转",
            "payoff_intensity": 5,
        }
    )
    with pytest.raises(ValidationError):
        Outline.model_validate(data)


def test_outline_rejects_extra_fields() -> None:
    data = deepcopy(outline_data())
    data["unexpected"] = True
    with pytest.raises(ValidationError):
        Outline.model_validate(data)
