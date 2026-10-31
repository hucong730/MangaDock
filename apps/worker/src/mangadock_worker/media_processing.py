import json
import os
from pathlib import Path

from mangadock_providers.media import run_media_command


def ffmpeg_bin() -> str:
    return os.getenv("FFMPEG_BIN", "ffmpeg")


async def probe_video(path) -> dict:
    output = await run_media_command(
        [
            os.getenv("FFPROBE_BIN", "ffprobe"),
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
    )
    return json.loads(output)


async def normalize_clip(source: Path, target: Path, duration_s: int) -> None:
    await run_media_command(
        [
            ffmpeg_bin(),
            "-y",
            "-i",
            str(source),
            "-t",
            str(duration_s),
            "-vf",
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(target),
        ]
    )


def manifest_path(path: Path) -> str:
    return str(path).replace("'", "'\\''")


def subtitle_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


async def compose_episode_media(
    clips: list[tuple[Path, int]],
    dubbing_lines: list[dict],
    output_dir: Path,
    episode: int,
    srt: str,
    vtt: str,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir = output_dir / "work"
    work_dir.mkdir(exist_ok=True)
    normalized = []
    for index, (source, duration) in enumerate(clips, start=1):
        target = work_dir / f"normalized_{index}.mp4"
        await normalize_clip(source, target, duration)
        normalized.append(target)
    manifest = work_dir / "concat.txt"
    manifest.write_text(
        "".join(f"file '{manifest_path(path)}'\n" for path in normalized),
        encoding="utf-8",
    )
    joined = work_dir / "joined.mp4"
    await run_media_command(
        [ffmpeg_bin(), "-y", "-f", "concat", "-safe", "0", "-i", str(manifest), "-c", "copy", str(joined)]
    )

    srt_path = output_dir / f"episode_{episode}.srt"
    vtt_path = output_dir / f"episode_{episode}.vtt"
    srt_path.write_text(srt, encoding="utf-8")
    vtt_path.write_text(vtt, encoding="utf-8")
    clean_path = output_dir / f"episode_{episode}_clean.mp4"
    audio_lines = [line for line in dubbing_lines if line["status"] == "done"]
    command = [ffmpeg_bin(), "-y", "-i", str(joined)]
    for line in audio_lines:
        command.extend(["-i", str(line["absolute_audio_path"])])
    if audio_lines:
        filters = []
        labels = []
        for index, line in enumerate(audio_lines, start=1):
            delay = round(line["start_s"] * 1000)
            filters.append(f"[{index}:a]adelay={delay}|{delay}[a{index}]")
            labels.append(f"[a{index}]")
        filters.append(
            f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0[aout]"
        )
        command.extend(
            ["-filter_complex", ";".join(filters), "-map", "0:v:0", "-map", "[aout]", "-c:a", "aac"]
        )
    else:
        command.extend(["-an"])
    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-t",
            str(sum(duration for _, duration in clips)),
            "-movflags",
            "+faststart",
            str(clean_path),
        ]
    )
    await run_media_command(command)

    style = (
        f"FontName={os.getenv('SUBTITLE_FONT', 'Noto Sans CJK SC')},"
        f"FontSize={os.getenv('SUBTITLE_FONT_SIZE', '24')},"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        f"BorderStyle=1,Outline={os.getenv('SUBTITLE_OUTLINE', '2')},"
        f"Alignment={os.getenv('SUBTITLE_ALIGNMENT', '2')}"
    )
    burned_path = output_dir / f"episode_{episode}.mp4"
    video_filter = (
        f"subtitles=filename={subtitle_path(srt_path)}:force_style='{style}'"
        if audio_lines
        else "null"
    )
    await run_media_command(
        [
            ffmpeg_bin(),
            "-y",
            "-i",
            str(clean_path),
            "-vf",
            video_filter,
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(burned_path),
        ]
    )
    return {
        "burned_path": burned_path,
        "clean_path": clean_path,
        "srt_path": srt_path,
        "vtt_path": vtt_path,
        "duration_s": sum(duration for _, duration in clips),
    }
