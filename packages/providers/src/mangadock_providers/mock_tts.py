import re
import uuid
import wave
from pathlib import Path

from mangadock_providers.tts_base import AudioResult, TTSProvider
from mangadock_providers.tts_exceptions import (
    TTSProviderAPIError,
    TTSProviderConfigurationError,
)

CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


class MockTTSProvider(TTSProvider):
    def __init__(self, output_dir: str, failures: int = 0) -> None:
        self._output_dir = Path(output_dir)
        self._failures = failures
        self.calls: list[dict[str, str]] = []

    async def synthesize(
        self,
        text: str,
        voice_profile: str,
        emotion: str,
    ) -> AudioResult:
        if not text.strip():
            raise TTSProviderConfigurationError("TTS text must not be empty")
        self.calls.append(
            {"text": text, "voice_profile": voice_profile, "emotion": emotion}
        )
        if self._failures:
            self._failures -= 1
            raise TTSProviderAPIError("injected mock TTS failure")
        character_count = len(CJK_PATTERN.findall(text)) or len(text.strip())
        duration_s = max(0.5, character_count / 4.5)
        sample_rate = 16000
        frame_count = round(duration_s * sample_rate)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / f"{uuid.uuid4().hex}.wav"
        with wave.open(str(path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(sample_rate)
            audio.writeframes(b"\x00\x00" * frame_count)
        actual_duration = frame_count / sample_rate
        return AudioResult(
            path=path,
            duration_s=actual_duration,
            format="wav",
            sample_rate=sample_rate,
            metadata={"mock": True, "voice_profile": voice_profile, "emotion": emotion},
        )
