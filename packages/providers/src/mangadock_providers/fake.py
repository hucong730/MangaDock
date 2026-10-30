import json
from collections.abc import Mapping, Sequence

from mangadock_providers.base import LLMProvider, ModelT


class FakeLLMProvider(LLMProvider):
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def chat(
        self,
        messages: Sequence[Mapping[str, str]],
        schema: type[ModelT],
    ) -> ModelT:
        self.calls.append({"messages": messages, "schema": schema})
        if schema.__name__ == "Outline":
            payload = {
                "synopsis": "调查记者林夏重返旧港，用一支录音笔揭开十年前的沉船真相。",
                "cast": [
                    {"name": "林夏", "role": "调查记者", "weight": 0.7},
                    {"name": "周衡", "role": "旧港集团继承人", "weight": 0.3},
                ],
                "episode_beat": [
                    {
                        "episode": 1,
                        "summary": "林夏收到匿名录音笔，里面传出父亲的声音。",
                        "payoff_type": "悬念钩子",
                        "payoff_intensity": 3,
                    },
                    {
                        "episode": 2,
                        "summary": "周衡承认伪造证词，并指出真正的主谋。",
                        "payoff_type": "身份反转",
                        "payoff_intensity": 5,
                    },
                ],
                "asset_list": ["旧港仓库", "银色录音笔"],
            }
        elif schema.__name__ == "Storyboard":
            payload = {
                "episodes": [
                    {
                        "episode": episode,
                        "segments": [
                            {
                                "index": 1,
                                "duration_s": 7,
                                "cuts": [
                                    {
                                        "index": 1,
                                        "duration_s": 3,
                                        "characters": ["林夏", "周衡"],
                                        "prompt": "<image1>林夏</image1><image2>周衡</image2>；林夏，辫梢红绳、藏青学生装；周衡，深灰西装、银框眼镜；旧港仓库夜景，双人中景",
                                        "camera": "缓慢推近",
                                        "line_refs": [{"scene": 1, "order": 2}],
                                        "scene_ref": None,
                                        "keyframe_image": None,
                                    },
                                    {
                                        "index": 2,
                                        "duration_s": 4,
                                        "characters": ["周衡"],
                                        "prompt": "<image1>周衡</image1>；周衡，深灰西装、银框眼镜；仓库门口，冷色侧光，中近景",
                                        "camera": "固定机位后拉",
                                        "line_refs": [{"scene": 1, "order": 4}],
                                        "scene_ref": None,
                                        "keyframe_image": None,
                                    },
                                ],
                            }
                        ],
                    }
                    for episode in (1, 2)
                ]
            }
        elif schema.__name__ == "CharacterBible":
            payload = {
                "characters": [
                    {
                        "name": "林夏",
                        "biography": "调查记者，十年前事故的幸存者。",
                        "prompt_zh": "林夏，辫梢红绳、藏青学生装，齐肩短发。",
                        "prompt_en": "Lin Xia, red ribbon braid, navy school uniform, shoulder-length hair",
                        "voice_prompt": "冷静克制的年轻女声，语速中等。",
                        "anchor_features": ["辫梢红绳", "藏青学生装", "齐肩短发", "琥珀色眼睛", "银色录音笔"],
                    },
                    {
                        "name": "周衡",
                        "biography": "旧港集团继承人，林夏昔日的证人。",
                        "prompt_zh": "周衡，深灰西装、银框眼镜。",
                        "prompt_en": "Zhou Heng, charcoal suit, silver-rimmed glasses",
                        "voice_prompt": "低沉克制的青年男声，语速偏慢。",
                        "anchor_features": ["深灰西装", "银框眼镜", "黑色短发", "银色袖扣", "冷峻眼神"],
                    },
                ]
            }
        elif schema.__name__ == "Episode":
            request = json.loads(messages[-1]["content"])
            payload = {
                "episode": request["episode"],
                "estimated_duration_s": 0,
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
                                "text": "你还是不肯说出真相吗？",
                            },
                            {
                                "order": 4,
                                "character": "周衡",
                                "emotion": "愧疚",
                                "text": "我来承认。",
                            },
                        ],
                    }
                ],
            }
        else:
            raise ValueError(f"Unsupported fake schema: {schema.__name__}")
        return schema.model_validate(payload)
