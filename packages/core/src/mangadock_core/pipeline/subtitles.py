from decimal import Decimal, ROUND_HALF_UP

from mangadock_core.schemas import Dubbing


def subtitle_time(value: float, decimal_separator: str) -> str:
    milliseconds = int(
        (Decimal(str(value)) * 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{decimal_separator}{millis:03d}"


def render_subtitles(dubbing: Dubbing, episode: int) -> tuple[str, str]:
    episode_asset = next(item for item in dubbing.episodes if item.episode == episode)
    lines = [line for line in episode_asset.lines if line.status == "done"]
    srt_blocks = [
        f"{index}\n{subtitle_time(line.start_s, ',')} --> {subtitle_time(line.end_s, ',')}\n{line.text}"
        for index, line in enumerate(lines, start=1)
    ]
    vtt_blocks = [
        f"{subtitle_time(line.start_s, '.')} --> {subtitle_time(line.end_s, '.')}\n{line.text}"
        for line in lines
    ]
    srt = "\n\n".join(srt_blocks)
    vtt = "WEBVTT\n\n" + "\n\n".join(vtt_blocks)
    if srt:
        srt += "\n"
    if vtt_blocks:
        vtt += "\n"
    return srt, vtt
