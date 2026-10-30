from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import TypeVar

from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)


class LLMProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: Sequence[Mapping[str, str]],
        schema: type[ModelT],
    ) -> ModelT:
        ...
