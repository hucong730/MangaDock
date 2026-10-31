import json
import os
import uuid
from pathlib import Path
from typing import Any

import edge_tts

from mangadock_providers.media import MediaToolError, probe_duration
from mangadock_providers.tts_base import AudioResult, TTSProvider
from mangadock_providers.tts_exceptions import (
    TTSProviderConfigurationError,
    TTSProviderResponseError,
    TTSProviderTransportError,
)

EMOTION_SETTINGS = {
    "震惊": ("+10%", "+2Hz"),
    "愧疚": ("-5%", "-2Hz"),
}


class EdgeTTSProvider(TTSProvider):
    def __init__(self, output_dir: str) -> None:
        self._output_dir = Path(output_dir)
        try:
            self._voice_map = json.loads(os.getenv("EDGE_TTS_VOICE_MAP", "{}"))
        except json.JSONDecodeError as error:
            raise TTSProviderConfigurationError("EDGE_TTS_VOICE_MAP must be valid JSON") from error
        if not isinstance(self._voice_map, dict):
            raise TTSProviderConfigurationError("EDGE_TTS_VOICE_MAP must be an object")

    def settings(self, voice_profile: str, emotion: str) -> tuple[str, str, str]:
        mapped: Any = self._voice_map.get(voice_profile)
        if isinstance(mapped, str):
            voice = mapped
        elif isinstance(mapped, dict):
            voice = mapped["voice"]
        elif "男" in voice_profile:
            voice = "zh-CN-YunxiNeural"
        else:
            voice = os.getenv("EDGE_TTS_DEFAULT_VOICE", "zh-CN-XiaoxiaoNeural")
        default_rate, default_pitch = EMOTION_SETTINGS.get(
            emotion,
            (os.getenv("EDGE_TTS_RATE", "+0%"), os.getenv("EDGE_TTS_PITCH", "+0Hz")),
        )
        rate = mapped.get("rate", default_rate) if isinstance(mapped, dict) else default_rate
        pitch = mapped.get("pitch", default_pitch) if isinstance(mapped, dict) else default_pitch
        return voice, rate, pitch

    async def synthesize(
        self,
        text: str,
        voice_profile: str,
        emotion: str,
    ) -> AudioResult:
        if not text.strip():
            raise TTSProviderConfigurationError("TTS text must not be empty")
        voice, rate, pitch = self.settings(voice_profile, emotion)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / f"{uuid.uuid4().hex}.mp3"
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
            await communicate.save(str(path))
        except Exception as error:
            raise TTSProviderTransportError(str(error)) from error
        try:
            duration = await probe_duration(path)
        except MediaToolError as error:
            raise TTSProviderResponseError(str(error)) from error
        return AudioResult(
            path=path,
            duration_s=duration,
            format="mp3",
            sample_rate=24000,
            metadata={"voice": voice, "rate": rate, "pitch": pitch},
        )
