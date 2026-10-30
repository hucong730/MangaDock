from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class ImageResult(BaseModel):
    path: Path
    width: int
    height: int
    format: str
    workflow_id: str
    metadata: dict[str, Any]


class ImageProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        reference_images: Sequence[str],
        size: tuple[int, int],
    ) -> ImageResult:
        ...
