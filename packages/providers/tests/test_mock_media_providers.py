import subprocess
import wave

import pytest

from mangadock_providers.media import MediaToolError, probe_duration, run_media_command
from mangadock_providers.mock_tts import MockTTSProvider
from mangadock_providers.mock_video import MockVideoProvider
from mangadock_providers.tts_exceptions import (
    TTSProviderAPIError,
    TTSProviderConfigurationError,
)
from mangadock_providers.video_exceptions import (
    VideoProviderAPIError,
    VideoProviderConfigurationError,
)


@pytest.mark.asyncio
async def test_mock_video_generates_playable_mp4(tmp_path) -> None:
    keyframe = tmp_path / "frame.png"
    keyframe.write_bytes(b"fake-keyframe")
    provider = MockVideoProvider(output_dir=str(tmp_path / "clips"))

    result = await provider.generate(str(keyframe), "测试镜头", 2, {})

    assert result.path.exists()
    assert result.format == "mp4"
    assert result.duration_s == 2
    assert await probe_duration(result.path) == pytest.approx(2, abs=0.1)


@pytest.mark.asyncio
async def test_mock_tts_wav_duration_matches_result(tmp_path) -> None:
    provider = MockTTSProvider(output_dir=str(tmp_path / "audio"))

    result = await provider.synthesize("你听见了吗", "冷静女声", "震惊")

    with wave.open(str(result.path), "rb") as audio:
        actual = audio.getnframes() / audio.getframerate()
        assert audio.getframerate() == 16000
    assert actual == pytest.approx(result.duration_s, abs=0.001)
    assert result.duration_s == pytest.approx(5 / 4.5, abs=0.001)


@pytest.mark.asyncio
async def test_mock_video_failure_and_duration_validation(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(VideoProviderConfigurationError):
        await MockVideoProvider(str(tmp_path)).generate("frame.png", "test", 1, {})
    with pytest.raises(VideoProviderAPIError, match="injected"):
        await MockVideoProvider(str(tmp_path), failures=1).generate(
            "frame.png", "test", 2, {}
        )

    async def failed_command(_):
        raise MediaToolError("ffmpeg failed")

    monkeypatch.setattr(
        "mangadock_providers.mock_video.run_media_command",
        failed_command,
    )
    with pytest.raises(VideoProviderAPIError, match="ffmpeg failed"):
        await MockVideoProvider(str(tmp_path)).generate("frame.png", "test", 2, {})


@pytest.mark.asyncio
async def test_mock_tts_failure_and_empty_text_validation(tmp_path) -> None:
    with pytest.raises(TTSProviderAPIError, match="injected"):
        await MockTTSProvider(str(tmp_path), failures=1).synthesize(
            "文本", "冷静女声", "平静"
        )
    with pytest.raises(TTSProviderConfigurationError):
        await MockTTSProvider(str(tmp_path)).synthesize(" ", "冷静女声", "平静")


@pytest.mark.asyncio
async def test_media_command_reports_execution_and_process_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(*args, **kwargs):
        raise OSError("missing")

    monkeypatch.setattr(subprocess, "run", missing)
    with pytest.raises(MediaToolError, match="Unable to execute"):
        await run_media_command(["ffmpeg"])

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", "bad"),
    )
    with pytest.raises(MediaToolError, match="bad"):
        await run_media_command(["ffmpeg"])


@pytest.mark.asyncio
async def test_probe_duration_rejects_invalid_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def invalid_output(_):
        return "not-json"

    monkeypatch.setattr(
        "mangadock_providers.media.run_media_command",
        invalid_output,
    )
    with pytest.raises(MediaToolError, match="Invalid ffprobe duration"):
        await probe_duration("video.mp4")
