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
