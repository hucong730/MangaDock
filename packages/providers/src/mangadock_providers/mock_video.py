import os
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from mangadock_providers.media import MediaToolError, run_media_command
from mangadock_providers.video_base import VideoProvider, VideoResult
from mangadock_providers.video_exceptions import (
    VideoProviderAPIError,
    VideoProviderConfigurationError,
)


class MockVideoProvider(VideoProvider):
    def __init__(self, output_dir: str, failures: int = 0) -> None:
        self._output_dir = Path(output_dir)
        self._failures = failures
        self.calls: list[dict[str, Any]] = []

    async def generate(
        self,
        keyframe_image: str,
        prompt: str,
        duration_s: int,
        config: Mapping[str, Any],
    ) -> VideoResult:
        if duration_s < 2 or duration_s > 5:
            raise VideoProviderConfigurationError("Mock video duration must be 2-5 seconds")
        self.calls.append(
            {"keyframe_image": keyframe_image, "prompt": prompt, "duration_s": duration_s}
        )
        if self._failures:
            self._failures -= 1
            raise VideoProviderAPIError("injected mock video failure")
        width = int(config.get("width", 320))
        height = int(config.get("height", 240))
        fps = int(config.get("fps", 24))
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / f"{uuid.uuid4().hex}.mp4"
        try:
            await run_media_command(
                [
                    os.getenv("FFMPEG_BIN", "ffmpeg"),
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    f"testsrc2=size={width}x{height}:rate={fps}",
                    "-t",
                    str(duration_s),
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    str(path),
                ]
            )
        except MediaToolError as error:
            raise VideoProviderAPIError(str(error)) from error
        return VideoResult(
            path=path,
            duration_s=duration_s,
            source_duration_s=duration_s,
            width=width,
            height=height,
            format="mp4",
            provider="mock",
            metadata={"mock": True},
        )
