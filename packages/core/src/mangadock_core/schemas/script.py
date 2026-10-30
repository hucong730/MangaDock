import math
import re

from pydantic import Field, model_validator

from mangadock_core.schemas.base import SchemaModel
from mangadock_core.schemas.outline import CastMember, ensure_unique_cast

CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


class ActionBeat(SchemaModel):
    order: int = Field(ge=1)
    text: str = Field(min_length=1)


class Line(SchemaModel):
    order: int = Field(ge=1)
    character: str = Field(min_length=1)
    emotion: str = Field(min_length=1)
    text: str = Field(min_length=1)


class Scene(SchemaModel):
    index: int = Field(ge=1)
    heading: str = Field(min_length=1)
    action_beats: list[ActionBeat] = Field(min_length=1)
    lines: list[Line]

    @model_validator(mode="after")
    def validate_alternating_order(self) -> "Scene":
        events = sorted(
            [(beat.order, "action") for beat in self.action_beats]
            + [(line.order, "line") for line in self.lines]
        )
        if [order for order, _ in events] != list(range(1, len(events) + 1)):
            raise ValueError("Scene order must be sequential from 1")
        kinds = [kind for _, kind in events]
        if kinds[0] != "action" or any(
            current == previous
            for previous, current in zip(kinds, kinds[1:])
        ):
            raise ValueError("Actions and lines must alternate, starting with action")
        return self


class Episode(SchemaModel):
    episode: int = Field(ge=1)
    estimated_duration_s: int
    scenes: list[Scene] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_episode(self) -> "Episode":
        indices = [scene.index for scene in self.scenes]
        if indices != list(range(1, len(self.scenes) + 1)):
            raise ValueError("Scene indices must be sequential from 1")
        chinese_characters = sum(
            len(CJK_PATTERN.findall(line.text))
            for scene in self.scenes
            for line in scene.lines
        )
        self.estimated_duration_s = math.ceil(chinese_characters / 4.5)
        return self


class Script(SchemaModel):
    cast: list[CastMember] = Field(min_length=1)
    episodes: list[Episode] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_script(self) -> "Script":
        ensure_unique_cast(self.cast)
        episode_numbers = [episode.episode for episode in self.episodes]
        if episode_numbers != list(range(1, len(self.episodes) + 1)):
            raise ValueError("Episode numbers must be sequential from 1")
        cast_names = {member.name for member in self.cast}
        for episode in self.episodes:
            for scene in episode.scenes:
                for line in scene.lines:
                    if line.character not in cast_names:
                        raise ValueError("Line character must belong to cast")
        return self
