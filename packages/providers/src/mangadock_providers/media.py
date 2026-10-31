import asyncio
import json
import os
import subprocess
from pathlib import Path


class MediaToolError(Exception):
    pass


async def run_media_command(arguments: list[str]) -> str:
    try:
        completed = await asyncio.to_thread(
            subprocess.run,
            arguments,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise MediaToolError(f"Unable to execute {arguments[0]}") from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise MediaToolError(f"{arguments[0]} failed: {detail}")
    return completed.stdout


async def probe_duration(path: str | Path) -> float:
    executable = os.getenv("FFPROBE_BIN", "ffprobe")
    output = await run_media_command(
        [
            executable,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ]
    )
    try:
        return float(json.loads(output)["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise MediaToolError(f"Invalid ffprobe duration for {path}") from error
