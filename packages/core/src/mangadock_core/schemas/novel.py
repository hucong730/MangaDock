from pydantic import Field, model_validator

from mangadock_core.schemas.base import SchemaModel


class Chapter(SchemaModel):
    index: int = Field(ge=1)
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)


class Novel(SchemaModel):
    title: str = Field(min_length=1)
    chapters: list[Chapter] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_chapter_sequence(self) -> "Novel":
        indices = [chapter.index for chapter in self.chapters]
        if indices != list(range(1, len(self.chapters) + 1)):
            raise ValueError("Chapter indices must be sequential from 1")
        return self
