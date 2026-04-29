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


from unittest.mock import patch, MagicMock

from engine.ffmpeg import run_ffmpeg, run_ffprobe


def test_run_ffmpeg_invokes_subprocess_with_resolved_binary(tmp_path: Path, monkeypatch):
    fake = tmp_path / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    fake.write_bytes(b"")
    monkeypatch.setenv("BWC_CLIPPER_FFMPEG_DIR", str(tmp_path))
    fake_completed = MagicMock(returncode=0, stdout="", stderr="")
    with patch("engine.ffmpeg.subprocess.run", return_value=fake_completed) as run_mock:
        run_ffmpeg(["-i", "in.mp4", "out.wav"])
    args, kwargs = run_mock.call_args
    cmd = args[0]
    assert Path(cmd[0]) == fake
    assert cmd[1:] == ["-i", "in.mp4", "out.wav"]
    assert kwargs["check"] is True
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True


def test_run_ffmpeg_raises_with_stderr_on_failure(tmp_path: Path, monkeypatch):
    import subprocess

    fake = tmp_path / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    fake.write_bytes(b"")
    monkeypatch.setenv("BWC_CLIPPER_FFMPEG_DIR", str(tmp_path))
    err = subprocess.CalledProcessError(1, ["ffmpeg"], stderr="boom: invalid input")
    with patch("engine.ffmpeg.subprocess.run", side_effect=err):
        with pytest.raises(RuntimeError) as exc_info:
            run_ffmpeg(["-i", "missing.mp4", "out.wav"])
    assert "boom: invalid input" in str(exc_info.value)


def test_run_ffprobe_returns_stdout(tmp_path: Path, monkeypatch):
    fake = tmp_path / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
    fake.write_bytes(b"")
    monkeypatch.setenv("BWC_CLIPPER_FFMPEG_DIR", str(tmp_path))
    fake_completed = MagicMock(returncode=0, stdout='{"streams":[]}', stderr="")
    with patch("engine.ffmpeg.subprocess.run", return_value=fake_completed):
        out = run_ffprobe(["-show_streams", "input.mp4"])
    assert out == '{"streams":[]}'
