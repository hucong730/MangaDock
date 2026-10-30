import re

from pydantic import Field, field_validator, model_validator

from mangadock_core.schemas.base import SchemaModel
from mangadock_core.schemas.character import CharacterBible
from mangadock_core.schemas.script import Script


class LineRef(SchemaModel):
    scene: int = Field(ge=1)
    order: int = Field(ge=1)


class KeyframeImage(SchemaModel):
    path: str = Field(min_length=1)
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    format: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)


class Cut(SchemaModel):
    index: int = Field(ge=1)
    duration_s: int = Field(ge=2, le=5)
    characters: list[str]
    prompt: str = Field(min_length=1)
    camera: str = Field(min_length=1)
    line_refs: list[LineRef]
    scene_ref: str | None = None
    keyframe_image: KeyframeImage | None = None

    @field_validator("scene_ref")
    @classmethod
    def validate_scene_ref(cls, value: str | None) -> str | None:
        if value is not None:
            raise ValueError("scene_ref is reserved for stage four")
        return value

    @field_validator("characters")
    @classmethod
    def validate_characters(cls, value: list[str]) -> list[str]:
        if len(value) > 4:
            raise ValueError("A cut supports at most 4 characters")
        if len(value) != len(set(value)):
            raise ValueError("Cut characters must be unique")
        return value


class Segment(SchemaModel):
    index: int = Field(ge=1)
    duration_s: int = Field(ge=0, le=15)
    cuts: list[Cut] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_segment(self) -> "Segment":
        indices = [cut.index for cut in self.cuts]
        if indices != list(range(1, len(self.cuts) + 1)):
            raise ValueError("Cut indices must be sequential from 1")
        self.duration_s = sum(cut.duration_s for cut in self.cuts)
        if self.duration_s > 15:
            raise ValueError("Segment duration must not exceed 15 seconds")
        return self


class EpisodeBoard(SchemaModel):
    episode: int = Field(ge=1)
    segments: list[Segment] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_segment_indices(self) -> "EpisodeBoard":
        indices = [segment.index for segment in self.segments]
        if indices != list(range(1, len(self.segments) + 1)):
            raise ValueError("Segment indices must be sequential from 1")
        return self


class Storyboard(SchemaModel):
    episodes: list[EpisodeBoard] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_episode_indices(self) -> "Storyboard":
        indices = [episode.episode for episode in self.episodes]
        if indices != list(range(1, len(self.episodes) + 1)):
            raise ValueError("Episode numbers must be sequential from 1")
        return self


def validate_storyboard(
    value: dict,
    script: Script,
    bible: CharacterBible,
) -> Storyboard:
    board = Storyboard.model_validate(value)
    if [episode.episode for episode in board.episodes] != [
        episode.episode for episode in script.episodes
    ]:
        raise ValueError("Storyboard must cover every script episode")

    anchors = {character.name: character.anchor_features for character in bible.characters}
    for board_episode, script_episode in zip(board.episodes, script.episodes):
        for segment in board_episode.segments:
            for cut in segment.cuts:
                for name in cut.characters:
                    if name not in anchors:
                        raise ValueError("Cut character must belong to cast")
                    if not any(feature in cut.prompt for feature in anchors[name]):
                        raise ValueError("Cut prompt must include an anchor feature")
                references = re.findall(r"<image(\d+)>([^<]+)</image\1>", cut.prompt)
                expected = [
                    (str(index), name)
                    for index, name in enumerate(cut.characters, start=1)
                ]
                if references != expected:
                    raise ValueError("Cut prompt image references must match character order")

        expected_lines = [
            (line.order, line)
            for scene in script_episode.scenes
            for line in scene.lines
        ]
        actual_refs = [
            ref
            for segment in board_episode.segments
            for cut in segment.cuts
            for ref in cut.line_refs
        ]
        expected_orders = [order for order, _ in expected_lines]
        actual_orders = [ref.order for ref in actual_refs]
        if actual_orders != expected_orders:
            raise ValueError("line_refs must cover every line once in order")
        for ref, (_, line) in zip(actual_refs, expected_lines):
            script_scene = next(
                (
                    scene
                    for scene in script_episode.scenes
                    if scene.index == ref.scene
                ),
                None,
            )
            if script_scene is None or line not in script_scene.lines:
                raise ValueError("line_refs must reference real script lines")
    return board
