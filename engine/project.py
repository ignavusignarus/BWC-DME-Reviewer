"""BWC Clipper project model.

A "project" in BWC Clipper is just a folder. This module owns the logic for
walking that folder for media files, detecting the per-file mode (BWC video
vs DME audio), and creating the hidden .bwcclipper/ cache directory.

Future milestones extend this module with per-source cache subdirectories
(Milestone 2) and clip persistence (Milestone 5).
"""

from __future__ import annotations

from pathlib import Path

# Extension allowlists. Lowercased on comparison; the source extension casing
# is preserved in the returned manifest.
VIDEO_EXTENSIONS = frozenset({"mp4", "mov", "mkv", "avi"})
AUDIO_EXTENSIONS = frozenset({"mp3", "wav", "m4a", "flac"})
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS


def walk_media_files(folder: Path) -> list[Path]:
    """Recursively enumerate media files under ``folder``.

    Returns a sorted list of absolute paths. Skips:
    - Files and directories whose name starts with a dot.
    - Files whose extension is not in ``MEDIA_EXTENSIONS`` (case-insensitive).

    Raises:
        FileNotFoundError: ``folder`` does not exist.
        NotADirectoryError: ``folder`` is not a directory.
    """
    folder = Path(folder).resolve()
    if not folder.exists():
        raise FileNotFoundError(folder)
    if not folder.is_dir():
        raise NotADirectoryError(folder)

    found: list[Path] = []
    for path in folder.rglob("*"):
        # rglob yields directories too — only files are media.
        if not path.is_file():
            continue
        # Skip anything inside or named as a dotfile/dotdir.
        if any(part.startswith(".") for part in path.relative_to(folder).parts):
            continue
        ext = path.suffix.lstrip(".").lower()
        if ext not in MEDIA_EXTENSIONS:
            continue
        found.append(path)

    found.sort()
    return found


def detect_mode(path: Path) -> str:
    """Return ``"bwc"`` for video media, ``"dme"`` for audio media.

    Mode detection is extension-based for Milestone 1. A future milestone may
    upgrade to ffprobe-based detection (e.g., to handle audio-only `.mp4`
    body-cam exports correctly), but the V1 heuristic is correct for the
    sample set we have today.

    Raises:
        ValueError: ``path`` has no recognized media extension.
    """
    ext = Path(path).suffix.lstrip(".").lower()
    if ext in VIDEO_EXTENSIONS:
        return "bwc"
    if ext in AUDIO_EXTENSIONS:
        return "dme"
    raise ValueError(f"unrecognized media extension: {path}")
