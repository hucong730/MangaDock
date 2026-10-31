from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class AudioResult(BaseModel):
    path: Path
    duration_s: float
    format: str
    sample_rate: int
    metadata: dict[str, Any]


class TTSProvider(ABC):
    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice_profile: str,
        emotion: str,
    ) -> AudioResult:
        ...
