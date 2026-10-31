from decimal import Decimal

from mangadock_core.schemas import Dubbing, DubbingLine, EpisodeBoard, Script, Storyboard


def build_dubbing_plan(
    script: Script,
    board: EpisodeBoard,
    episode: int,
) -> list[DubbingLine]:
    script_episode = next(item for item in script.episodes if item.episode == episode)
    script_lines = {
        (scene.index, line.order): line
        for scene in script_episode.scenes
        for line in scene.lines
    }
    return [
        DubbingLine(
            line_id=f"{episode}:{ref.scene}:{ref.order}",
            scene=ref.scene,
            order=ref.order,
            segment=segment.index,
            cut=cut.index,
            character=script_lines[(ref.scene, ref.order)].character,
            text=script_lines[(ref.scene, ref.order)].text,
            emotion=script_lines[(ref.scene, ref.order)].emotion,
        )
        for segment in board.segments
        for cut in segment.cuts
        for ref in cut.line_refs
    ]


def apply_dubbing_timing(
    lines: list[DubbingLine],
    board: EpisodeBoard,
) -> list[DubbingLine]:
    cut_start = Decimal("0")
    for segment in board.segments:
        for cut in segment.cuts:
            cursor = cut_start
            cut_lines = [
                line for line in lines if line.segment == segment.index and line.cut == cut.index
            ]
            for line in cut_lines:
                duration = Decimal(str(line.duration_s))
                line.start_s = float(cursor)
                cursor += duration
                line.end_s = float(cursor)
                if line.status == "done" and cursor > cut_start + Decimal(cut.duration_s):
                    raise ValueError("Done dubbing line exceeds its cut")
            cut_start += Decimal(cut.duration_s)
    return lines


def validate_dubbing(value: dict, script: Script, board: Storyboard) -> Dubbing:
    dubbing = Dubbing.model_validate(value)
    if [item.episode for item in dubbing.episodes] != [
        item.episode for item in board.episodes
    ]:
        raise ValueError("Dubbing must cover every storyboard episode")
    for dubbing_episode, board_episode, script_episode in zip(
        dubbing.episodes, board.episodes, script.episodes
    ):
        expected = [
            (ref.scene, ref.order)
            for segment in board_episode.segments
            for cut in segment.cuts
            for ref in cut.line_refs
        ]
        actual = [(line.scene, line.order) for line in dubbing_episode.lines]
        if actual != expected:
            raise ValueError("Dubbing must cover every line once in order")
        script_lines = {
            (scene.index, line.order): line
            for scene in script_episode.scenes
            for line in scene.lines
        }
        cut_starts = {}
        cut_durations = {}
        cursor = Decimal("0")
        for segment in board_episode.segments:
            for cut in segment.cuts:
                cut_starts[(segment.index, cut.index)] = cursor
                cut_durations[(segment.index, cut.index)] = Decimal(cut.duration_s)
                cursor += Decimal(cut.duration_s)
        for line in dubbing_episode.lines:
            source = script_lines[(line.scene, line.order)]
            if line.text != source.text or line.character != source.character:
                raise ValueError("Dubbing line content must match Script")
            if line.status != "done":
                continue
            start = cut_starts[(line.segment, line.cut)]
            if (
                Decimal(str(line.start_s)) < start
                or Decimal(str(line.end_s))
                > start + cut_durations[(line.segment, line.cut)]
            ):
                raise ValueError("Done dubbing line exceeds its cut")
    return dubbing
