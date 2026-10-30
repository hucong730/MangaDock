from pydantic import Field, model_validator

from mangadock_core.schemas.base import SchemaModel


class CastMember(SchemaModel):
    name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    weight: float = Field(ge=0, le=1)


class EpisodeBeat(SchemaModel):
    episode: int = Field(ge=1)
    summary: str = Field(min_length=1)
    payoff_type: str = Field(min_length=1)
    payoff_intensity: int = Field(ge=1, le=5)


def ensure_unique_cast(cast: list[CastMember]) -> None:
    names = [member.name for member in cast]
    if len(names) != len(set(names)):
        raise ValueError("Cast names must be unique")


class Outline(SchemaModel):
    synopsis: str = Field(min_length=1)
    cast: list[CastMember] = Field(min_length=1)
    episode_beat: list[EpisodeBeat] = Field(min_length=1)
    asset_list: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_outline(self) -> "Outline":
        if any(not asset for asset in self.asset_list):
            raise ValueError("Asset names must not be blank")
        ensure_unique_cast(self.cast)
        episodes = [beat.episode for beat in self.episode_beat]
        if episodes != list(range(1, len(self.episode_beat) + 1)):
            raise ValueError("Episode numbers must be sequential from 1")
        major_episodes = [
            beat.episode
            for beat in self.episode_beat
            if beat.payoff_intensity == 5
        ]
        if any(
            later - earlier > 8
            for earlier, later in zip(major_episodes, major_episodes[1:])
        ):
            raise ValueError("Major payoff intervals must not exceed 8 episodes")
        return self
