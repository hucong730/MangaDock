from mangadock_core.pipeline.dubbing import apply_dubbing_timing, build_dubbing_plan
from mangadock_core.pipeline.subtitles import render_subtitles
from mangadock_core.schemas import Dubbing, EpisodeBoard
from test_storyboard_schema import script, storyboard_data


def dubbing() -> Dubbing:
    board = EpisodeBoard.model_validate(storyboard_data()["episodes"][0])
    lines = build_dubbing_plan(script(), board, 1)
    durations = [2.667, 1.333]
    for line, duration in zip(lines, durations):
        line.status = "done"
        line.audio_path = "audio.wav"
        line.duration_s = duration
    apply_dubbing_timing(lines, board)
    return Dubbing(episodes=[{"episode": 1, "lines": lines}])


def test_srt_and_vtt_use_measured_dubbing_times() -> None:
    srt, vtt = render_subtitles(dubbing(), 1)

    assert "1\n00:00:00,000 --> 00:00:02,667\n你在说谎" in srt
    assert "2\n00:00:03,000 --> 00:00:04,333\n我承认" in srt
    assert "00:00:00.000 --> 00:00:02.667\n你在说谎" in vtt
    assert vtt.startswith("WEBVTT")


def test_empty_dialogue_produces_empty_srt_and_valid_vtt() -> None:
    srt, vtt = render_subtitles(Dubbing(episodes=[{"episode": 1, "lines": []}]), 1)

    assert srt == ""
    assert vtt == "WEBVTT\n\n"
