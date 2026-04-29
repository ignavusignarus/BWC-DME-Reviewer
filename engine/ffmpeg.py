"""ffmpeg / ffprobe binary discovery and subprocess wrappers.

The Electron main process downloads ffmpeg.exe and ffprobe.exe to a per-user
directory and passes the path to the engine via the BWC_CLIPPER_FFMPEG_DIR
environment variable. If that variable is not set (e.g., when running tests
or when the user has system ffmpeg installed), fall back to searching PATH.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

FFMPEG_BINARY = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
FFPROBE_BINARY = "ffprobe.exe" if os.name == "nt" else "ffprobe"


def _find_binary(name: str) -> Path:
    bundled_dir = os.environ.get("BWC_CLIPPER_FFMPEG_DIR")
    if bundled_dir:
        candidate = Path(bundled_dir) / name
        if candidate.is_file():
            return candidate
    on_path = shutil.which(name)
    if on_path:
        return Path(on_path)
    raise FileNotFoundError(
        f"{name} not found — checked BWC_CLIPPER_FFMPEG_DIR={bundled_dir!r} and system PATH"
    )


def find_ffmpeg() -> Path:
    return _find_binary(FFMPEG_BINARY)


def find_ffprobe() -> Path:
    return _find_binary(FFPROBE_BINARY)


import subprocess


def run_ffmpeg(args: list[str], *, timeout: float | None = None) -> str:
    """Run ffmpeg with the given arguments. Returns captured stdout.

    Raises:
        RuntimeError: ffmpeg exited non-zero. The exception message includes
            the captured stderr.
    """
    binary = find_ffmpeg()
    try:
        result = subprocess.run(
            [str(binary), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffmpeg failed (exit {exc.returncode}): {exc.stderr}") from exc


def run_ffprobe(args: list[str], *, timeout: float | None = None) -> str:
    """Run ffprobe with the given arguments. Returns captured stdout."""
    binary = find_ffprobe()
    try:
        result = subprocess.run(
            [str(binary), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffprobe failed (exit {exc.returncode}): {exc.stderr}") from exc


import json


# Required keys we expect in the loudnorm JSON output.
_LOUDNORM_KEYS = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")


def run_loudnorm_measure(input_path: Path) -> dict[str, str]:
    """First pass of two-pass loudnorm. Returns measured values as a dict
    of strings (kept as strings because ffmpeg's second pass takes them
    through unchanged on the command line).

    Per brief §4.2: ``loudnorm=I=-16:LRA=11:TP=-1.5``.
    """
    binary = find_ffmpeg()
    cmd = [
        str(binary),
        "-hide_banner",
        "-i", str(input_path),
        "-af", "loudnorm=I=-16:LRA=11:TP=-1.5:print_format=json",
        "-f", "null",
        "-",
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffmpeg loudnorm-measure failed: {exc.stderr}") from exc

    # ffmpeg writes the JSON object near the end of stderr. Find the last
    # balanced single-level { ... } block and parse it. ffmpeg's loudnorm
    # output is always a flat object; if a future version emits nested JSON
    # this regex will need to grow.
    match = re.search(r"\{[^{}]*\}", result.stderr, re.DOTALL)
    if match is None:
        raise RuntimeError(
            "loudnorm did not emit a JSON measurement block. "
            f"Last stderr lines:\n{result.stderr[-500:]}"
        )
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"loudnorm JSON parse failed: {exc}") from exc

    return {k: str(data[k]) for k in _LOUDNORM_KEYS if k in data}


def probe_audio_tracks(path: Path) -> list[dict]:
    """Run ffprobe to enumerate audio tracks in ``path``.

    Returns a list of dicts (one per audio stream) with keys:
    index, codec_name, sample_rate, channels, duration_seconds.
    Returns [] if the file has no audio streams.
    """
    output = run_ffprobe([
        "-v", "error",
        "-show_streams",
        "-select_streams", "a",
        "-of", "json",
        str(path),
    ])
    data = json.loads(output)
    tracks = []
    for stream in data.get("streams", []):
        if stream.get("codec_type") != "audio":
            continue
        duration_str = stream.get("duration")
        tracks.append({
            "index": int(stream["index"]),
            "codec_name": stream.get("codec_name", ""),
            "sample_rate": int(stream.get("sample_rate", 0)),
            "channels": int(stream.get("channels", 0)),
            "duration_seconds": float(duration_str) if duration_str else None,
        })
    return tracks
