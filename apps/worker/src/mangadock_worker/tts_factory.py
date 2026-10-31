import os

from mangadock_providers import EdgeTTSProvider, MockTTSProvider, TTSProvider


def tts_for_project(project_id: int, episode: int, output_dir: str) -> TTSProvider:
    mode = os.getenv("MANGADOCK_TTS_MODE", "fake").lower()
    if mode == "fake":
        return MockTTSProvider(output_dir=output_dir)
    if mode == "live":
        return EdgeTTSProvider(output_dir=output_dir)
    raise ValueError("MANGADOCK_TTS_MODE must be fake or live")
