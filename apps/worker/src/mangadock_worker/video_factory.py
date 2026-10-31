import os
from collections.abc import Mapping
from typing import Any

from mangadock_persistence.models import VideoProviderRecord
from mangadock_providers import (
    MinimaxH3Provider,
    MockVideoProvider,
    SeedanceProvider,
    VideoProvider,
    WanProvider,
)
from mangadock_providers.video_prompts import (
    build_minimax_h3_prompt,
    build_seedance_prompt,
    build_wan_prompt,
)


def video_mode() -> str:
    mode = os.getenv("MANGADOCK_VIDEO_MODE", "fake").lower()
    if mode not in {"fake", "live"}:
        raise ValueError("MANGADOCK_VIDEO_MODE must be fake or live")
    return mode


def video_for_record(
    record: VideoProviderRecord | None,
    output_dir: str,
) -> VideoProvider:
    if video_mode() == "fake":
        return MockVideoProvider(output_dir=output_dir)
    if record is None:
        raise ValueError("Video provider route is not configured")
    api_key = os.getenv(record.api_key_env, "")
    if record.kind == "wan":
        return WanProvider(
            base_url=record.base_url,
            api_key=api_key,
            output_dir=output_dir,
            timeout_s=float(record.config_json.get("timeout_s", 300)),
        )
    if record.kind == "seedance":
        return SeedanceProvider(
            base_url=record.base_url,
            model=record.model,
            api_key=api_key,
            output_dir=output_dir,
            timeout_s=float(record.config_json.get("timeout_s", 300)),
        )
    if record.kind == "minimax_h3":
        return MinimaxH3Provider(
            base_url=record.base_url,
            model=record.model,
            api_key=api_key,
            output_dir=output_dir,
            timeout_s=float(record.config_json.get("timeout_s", 300)),
        )
    raise ValueError(f"Unsupported video provider kind: {record.kind}")


def build_video_prompt(
    record: VideoProviderRecord | None,
    segment: Mapping[str, Any],
    cut_index: int,
) -> str:
    kind = record.kind if record is not None else "wan"
    if kind == "seedance":
        return build_seedance_prompt(segment, cut_index)
    if kind == "minimax_h3":
        return build_minimax_h3_prompt(segment, cut_index)
    return build_wan_prompt(segment, cut_index)
