"""Tests for engine.project."""
from pathlib import Path

import pytest

from engine.project import walk_media_files


def _touch(path: Path):
    """Create an empty file, including parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def test_walk_media_files_finds_video_and_audio(tmp_path: Path):
    _touch(tmp_path / "officer-garcia.mp4")
    _touch(tmp_path / "doctor.MP3")
    _touch(tmp_path / "notes.txt")  # not media — should be skipped
    paths = walk_media_files(tmp_path)
    basenames = sorted(p.name for p in paths)
    assert basenames == ["doctor.MP3", "officer-garcia.mp4"]


def test_walk_media_files_recursive(tmp_path: Path):
    _touch(tmp_path / "incident-001" / "officer-a.mp4")
    _touch(tmp_path / "incident-002" / "officer-b.mov")
    paths = walk_media_files(tmp_path)
    basenames = sorted(p.name for p in paths)
    assert basenames == ["officer-a.mp4", "officer-b.mov"]


def test_walk_media_files_skips_dot_directories(tmp_path: Path):
    """Hidden directories like .bwcclipper/ must not be traversed."""
    _touch(tmp_path / ".bwcclipper" / "some-source" / "transcript.json")
    _touch(tmp_path / "real.mp4")
    paths = walk_media_files(tmp_path)
    basenames = [p.name for p in paths]
    assert basenames == ["real.mp4"]


def test_walk_media_files_skips_dotfiles(tmp_path: Path):
    _touch(tmp_path / ".DS_Store")
    _touch(tmp_path / "real.mp4")
    paths = walk_media_files(tmp_path)
    basenames = [p.name for p in paths]
    assert basenames == ["real.mp4"]


def test_walk_media_files_recognizes_supported_extensions(tmp_path: Path):
    """Spec extensions: .mp4 .mov .mkv .avi (video), .mp3 .MP3 .wav .m4a .flac (audio).

    Each filename is unique (basename + extension) to avoid Windows NTFS
    case-insensitive collisions — e.g., ``a.mp3`` and ``a.MP3`` resolve to
    the same file on Windows even though they're distinct on POSIX.
    """
    fixtures = [
        "video1.mp4", "video2.mov", "video3.mkv", "video4.avi",
        "audio1.mp3", "audio2.MP3", "audio3.wav", "audio4.m4a", "audio5.flac",
    ]
    for f in fixtures:
        _touch(tmp_path / f)
    paths = walk_media_files(tmp_path)
    basenames = sorted(p.name for p in paths)
    assert basenames == sorted(fixtures)


def test_walk_media_files_returns_sorted(tmp_path: Path):
    """Result is sorted by absolute path for deterministic UI ordering."""
    _touch(tmp_path / "z.mp4")
    _touch(tmp_path / "a.mp4")
    _touch(tmp_path / "m" / "b.mp4")
    paths = walk_media_files(tmp_path)
    basenames = [p.name for p in paths]
    assert basenames == sorted(basenames)


def test_walk_media_files_raises_on_missing_path(tmp_path: Path):
    missing = tmp_path / "does-not-exist"
    with pytest.raises(FileNotFoundError):
        walk_media_files(missing)


def test_walk_media_files_raises_on_file_path(tmp_path: Path):
    f = tmp_path / "x.mp4"
    f.write_bytes(b"")
    with pytest.raises(NotADirectoryError):
        walk_media_files(f)


from engine.project import detect_mode


def test_detect_mode_video_is_bwc(tmp_path: Path):
    f = tmp_path / "x.mp4"
    f.write_bytes(b"")
    assert detect_mode(f) == "bwc"


def test_detect_mode_audio_is_dme(tmp_path: Path):
    f = tmp_path / "x.mp3"
    f.write_bytes(b"")
    assert detect_mode(f) == "dme"


def test_detect_mode_uppercase_extension(tmp_path: Path):
    f = tmp_path / "x.MP3"
    f.write_bytes(b"")
    assert detect_mode(f) == "dme"


def test_detect_mode_unknown_extension_raises(tmp_path: Path):
    f = tmp_path / "x.xyz"
    f.write_bytes(b"")
    with pytest.raises(ValueError):
        detect_mode(f)
