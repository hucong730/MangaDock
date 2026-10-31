import pytest

from mangadock_providers.edge_tts import EdgeTTSProvider
from mangadock_providers.tts_exceptions import (
    TTSProviderConfigurationError,
    TTSProviderResponseError,
    TTSProviderTransportError,
)


class FakeCommunicate:
    calls = []
    error = None

    def __init__(self, text, voice, rate, pitch):
        self.text = text
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.calls.append(
            {"text": text, "voice": voice, "rate": rate, "pitch": pitch}
        )

    async def save(self, path):
        if self.error:
            raise self.error
        with open(path, "wb") as output:
            output.write(b"mp3")


@pytest.fixture(autouse=True)
def reset_calls(monkeypatch: pytest.MonkeyPatch):
    FakeCommunicate.calls = []
    FakeCommunicate.error = None
    monkeypatch.setattr(
        "mangadock_providers.edge_tts.edge_tts.Communicate",
        FakeCommunicate,
    )


@pytest.mark.asyncio
async def test_edge_tts_maps_voice_profile_and_emotion(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def measured(_):
        return 2.667

    monkeypatch.setattr(
        "mangadock_providers.edge_tts.probe_duration",
        measured,
    )
    monkeypatch.setenv(
        "EDGE_TTS_VOICE_MAP",
        '{"林夏": "zh-CN-XiaoyiNeural", "周衡": {"voice": "zh-CN-YunjianNeural"}}',
    )
    provider = EdgeTTSProvider(str(tmp_path))

    result = await provider.synthesize("台词", "林夏", "震惊")
    await provider.synthesize("另一句", "周衡", "愧疚")

    assert result.duration_s == 2.667
    assert result.format == "mp3"
    assert FakeCommunicate.calls == [
        {
            "text": "台词",
            "voice": "zh-CN-XiaoyiNeural",
            "rate": "+10%",
            "pitch": "+2Hz",
        },
        {
            "text": "另一句",
            "voice": "zh-CN-YunjianNeural",
            "rate": "-5%",
            "pitch": "-2Hz",
        },
    ]


@pytest.mark.asyncio
async def test_edge_tts_defaults_to_gender_voice(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def measured(_):
        return 1.0

    monkeypatch.setattr(
        "mangadock_providers.edge_tts.probe_duration",
        measured,
    )
    provider = EdgeTTSProvider(str(tmp_path))

    await provider.synthesize("台词", "低沉男声", "平静")

    assert FakeCommunicate.calls[0]["voice"] == "zh-CN-YunxiNeural"
    assert FakeCommunicate.calls[0]["rate"] == "+0%"


@pytest.mark.asyncio
async def test_edge_tts_maps_synthesis_failure(tmp_path) -> None:
    FakeCommunicate.error = RuntimeError("offline")
    provider = EdgeTTSProvider(str(tmp_path))

    with pytest.raises(TTSProviderTransportError, match="offline"):
        await provider.synthesize("台词", "冷静女声", "平静")


@pytest.mark.asyncio
async def test_edge_tts_rejects_bad_voice_map_and_probe_failure(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EDGE_TTS_VOICE_MAP", "not-json")
    with pytest.raises(TTSProviderConfigurationError):
        EdgeTTSProvider(str(tmp_path))
    monkeypatch.setenv("EDGE_TTS_VOICE_MAP", "[]")
    with pytest.raises(TTSProviderConfigurationError):
        EdgeTTSProvider(str(tmp_path))

    monkeypatch.setenv("EDGE_TTS_VOICE_MAP", "{}")
    async def failed_probe(_):
        from mangadock_providers.media import MediaToolError
        raise MediaToolError("bad media")

    monkeypatch.setattr(
        "mangadock_providers.edge_tts.probe_duration",
        failed_probe,
    )
    provider = EdgeTTSProvider(str(tmp_path))
    with pytest.raises(TTSProviderResponseError):
        await provider.synthesize("台词", "冷静女声", "平静")
    with pytest.raises(TTSProviderConfigurationError):
        await provider.synthesize(" ", "冷静女声", "平静")
