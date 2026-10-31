from abc import ABC, abstractmethod
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class VideoResult(BaseModel):
    path: Path
    duration_s: float
    source_duration_s: float
    width: int
    height: int
    format: str
    provider: str
    metadata: dict[str, Any]


class VideoProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        keyframe_image: str,
        prompt: str,
        duration_s: int,
        config: Mapping[str, Any],
    ) -> VideoResult:
        ...
