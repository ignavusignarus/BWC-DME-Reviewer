"""Tests for engine.ffmpeg path discovery."""
import os
from pathlib import Path

import pytest

from engine.ffmpeg import find_ffmpeg, find_ffprobe


def test_find_ffmpeg_uses_bwc_clipper_ffmpeg_dir(tmp_path: Path, monkeypatch):
    fake = tmp_path / "ffmpeg.exe" if os.name == "nt" else tmp_path / "ffmpeg"
    fake.write_bytes(b"")
    monkeypatch.setenv("BWC_CLIPPER_FFMPEG_DIR", str(tmp_path))
    assert find_ffmpeg() == fake


def test_find_ffprobe_uses_bwc_clipper_ffmpeg_dir(tmp_path: Path, monkeypatch):
    fake = tmp_path / "ffprobe.exe" if os.name == "nt" else tmp_path / "ffprobe"
    fake.write_bytes(b"")
    monkeypatch.setenv("BWC_CLIPPER_FFMPEG_DIR", str(tmp_path))
    assert find_ffprobe() == fake


def test_find_ffmpeg_raises_if_not_found(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BWC_CLIPPER_FFMPEG_DIR", str(tmp_path))
    monkeypatch.setenv("PATH", "")  # no system fallback
    with pytest.raises(FileNotFoundError):
        find_ffmpeg()


def test_find_ffmpeg_falls_back_to_path(tmp_path: Path, monkeypatch):
    """If BWC_CLIPPER_FFMPEG_DIR not set, search PATH."""
    monkeypatch.delenv("BWC_CLIPPER_FFMPEG_DIR", raising=False)
    fake_dir = tmp_path / "binstub"
    fake_dir.mkdir()
    fake = fake_dir / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    fake.write_bytes(b"")
    monkeypatch.setenv("PATH", str(fake_dir))
    assert find_ffmpeg() == fake
