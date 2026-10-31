from pathlib import Path

import pytest
from pydantic import ValidationError

from mangadock_core.fingerprints import dependency_fingerprint
from mangadock_core.pipeline.dubbing import (
    apply_dubbing_timing,
    build_dubbing_plan,
    validate_dubbing,
)
from mangadock_core.schemas import Compose, Dubbing, EpisodeBoard, Render, Storyboard
from test_storyboard_schema import script, storyboard_data


def board() -> EpisodeBoard:
    return EpisodeBoard.model_validate(storyboard_data()["episodes"][0])


def storyboard() -> Storyboard:
    return Storyboard(episodes=[board()])


def test_dubbing_plan_covers_every_line_with_stable_ids() -> None:
    lines = build_dubbing_plan(script(), board(), 1)

    assert [line.line_id for line in lines] == ["1:1:2", "1:1:4"]
    assert [(line.segment, line.cut) for line in lines] == [(1, 1), (1, 2)]
    assert [line.text for line in lines] == ["你在说谎", "我承认"]


def test_dubbing_timing_allows_multiple_lines_in_one_cut() -> None:
    lines = build_dubbing_plan(script(), board(), 1)
    lines[1].segment = 1
    lines[1].cut = 1
    for line in lines:
        line.status = "done"
        line.audio_path = "audio.wav"
        line.duration_s = 1.25

    apply_dubbing_timing(lines, board())

    assert [(line.start_s, line.end_s) for line in lines] == [(0, 1.25), (1.25, 2.5)]
    validate_dubbing(Dubbing(episodes=[{"episode": 1, "lines": lines}]), script(), storyboard())


def test_failed_overlong_line_is_legal_but_done_overlong_line_fails() -> None:
    lines = build_dubbing_plan(script(), board(), 1)
    for line, duration in zip(lines, [3, 5]):
        line.audio_path = "audio.wav"
        line.duration_s = duration
    lines[0].status = "done"
    lines[1].status = "failed"
    apply_dubbing_timing(lines, board())

    validate_dubbing(Dubbing(episodes=[{"episode": 1, "lines": lines}]), script(), storyboard())

    lines[1].status = "done"
    with pytest.raises(ValueError, match="cut"):
        validate_dubbing(Dubbing(episodes=[{"episode": 1, "lines": lines}]), script(), storyboard())


def test_dubbing_rejects_bad_timing_and_missing_lines() -> None:
    lines = build_dubbing_plan(script(), board(), 1)
    lines[0].status = "done"
    lines[0].audio_path = "audio.wav"
    lines[0].duration_s = 1
    lines[0].end_s = 2
    with pytest.raises(ValidationError, match="end_s"):
        Dubbing(episodes=[{"episode": 1, "lines": lines}])

    fresh_lines = build_dubbing_plan(script(), board(), 1)
    with pytest.raises(ValueError, match="cover"):
        validate_dubbing(
            Dubbing(episodes=[{"episode": 1, "lines": fresh_lines[:1]}]),
            script(),
            storyboard(),
        )


def test_render_and_compose_done_assets_require_paths() -> None:
    with pytest.raises(ValidationError, match="clip_path"):
        Render.model_validate(
            {
                "episodes": [{
                    "episode": 1,
                    "segments": [{
                        "index": 1,
                        "cuts": [{
                            "index": 1,
                            "duration_s": 3,
                            "status": "done",
                            "attempt_count": 1,
                            "source_fingerprint": "abc",
                        }],
                    }],
                }]
            }
        )

    with pytest.raises(ValidationError, match="burned_path"):
        Compose.model_validate(
            {"episodes": [{"episode": 1, "status": "done", "source_fingerprint": "abc"}]}
        )


def test_dependency_fingerprint_is_canonical_and_content_sensitive() -> None:
    first = {"voice": "冷静", "nested": {"b": 2, "a": 1}}
    reordered = {"nested": {"a": 1, "b": 2}, "voice": "冷静"}

    assert dependency_fingerprint(first) == dependency_fingerprint(reordered)
    assert dependency_fingerprint(first) != dependency_fingerprint({**first, "voice": "激动"})


def test_valid_render_and_compose_assets() -> None:
    render = Render.model_validate(
        {
            "episodes": [{
                "episode": 1,
                "segments": [{
                    "index": 1,
                    "cuts": [{
                        "index": 1,
                        "duration_s": 3,
                        "status": "done",
                        "clip_path": "clip.mp4",
                    }],
                }],
            }]
        }
    )
    compose = Compose.model_validate(
        {
            "episodes": [{
                "episode": 1,
                "status": "done",
                "burned_path": "burned.mp4",
                "clean_path": "clean.mp4",
                "srt_path": "episode.srt",
                "vtt_path": "episode.vtt",
            }]
        }
    )

    assert render.episodes[0].segments[0].cuts[0].clip_path == "clip.mp4"
    assert compose.episodes[0].width == 1920


def test_dubbing_rejects_overlong_apply_episode_mismatch_and_text_change() -> None:
    lines = build_dubbing_plan(script(), board(), 1)
    for line in lines:
        line.status = "done"
        line.audio_path = "audio.wav"
        line.duration_s = 5
    with pytest.raises(ValueError, match="exceeds"):
        apply_dubbing_timing(lines, board())

    with pytest.raises(ValueError, match="episode"):
        validate_dubbing(
            Dubbing(episodes=[{"episode": 2, "lines": []}]), script(), storyboard()
        )

    fresh = build_dubbing_plan(script(), board(), 1)
    fresh[0].text = "改写的台词"
    with pytest.raises(ValueError, match="match Script"):
        validate_dubbing(
            Dubbing(episodes=[{"episode": 1, "lines": fresh}]), script(), storyboard()
        )

    missing_audio = build_dubbing_plan(script(), board(), 1)[0]
    missing_audio.status = "done"
    with pytest.raises(ValidationError, match="audio_path"):
        Dubbing(episodes=[{"episode": 1, "lines": [missing_audio]}])


def test_fingerprint_supports_models_paths_and_sequences() -> None:
    model = board()

    assert dependency_fingerprint(model) == dependency_fingerprint(model.model_dump())
    assert dependency_fingerprint(Path("a/b.png")) == dependency_fingerprint("a/b.png")
    assert dependency_fingerprint((Path("a"), 1)) == dependency_fingerprint(["a", 1])
