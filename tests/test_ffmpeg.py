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


import json as _json

from engine.ffmpeg import probe_audio_tracks


def test_probe_audio_tracks_parses_stream_list(tmp_path: Path, monkeypatch):
    fake = tmp_path / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
    fake.write_bytes(b"")
    monkeypatch.setenv("BWC_CLIPPER_FFMPEG_DIR", str(tmp_path))

    ffprobe_output = _json.dumps({
        "streams": [
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 2,
                "duration": "120.5",
            },
            {
                "index": 2,
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 1,
                "duration": "120.5",
            },
        ]
    })
    fake_completed = MagicMock(returncode=0, stdout=ffprobe_output, stderr="")
    with patch("engine.ffmpeg.subprocess.run", return_value=fake_completed):
        tracks = probe_audio_tracks(Path("input.mp4"))
    assert len(tracks) == 2
    assert tracks[0] == {
        "index": 1, "codec_name": "aac",
        "sample_rate": 48000, "channels": 2, "duration_seconds": 120.5,
    }
    assert tracks[1]["channels"] == 1


def test_probe_audio_tracks_returns_empty_for_no_audio(tmp_path: Path, monkeypatch):
    fake = tmp_path / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
    fake.write_bytes(b"")
    monkeypatch.setenv("BWC_CLIPPER_FFMPEG_DIR", str(tmp_path))
    fake_completed = MagicMock(returncode=0, stdout='{"streams":[]}', stderr="")
    with patch("engine.ffmpeg.subprocess.run", return_value=fake_completed):
        tracks = probe_audio_tracks(Path("video-only.mp4"))
    assert tracks == []


def test_probe_audio_tracks_handles_missing_optional_fields(tmp_path: Path, monkeypatch):
    """Some sources omit duration in stream metadata; treat as None."""
    fake = tmp_path / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
    fake.write_bytes(b"")
    monkeypatch.setenv("BWC_CLIPPER_FFMPEG_DIR", str(tmp_path))
    fake_completed = MagicMock(
        returncode=0,
        stdout=_json.dumps({"streams": [{
            "index": 0, "codec_type": "audio", "codec_name": "pcm_s16le",
            "sample_rate": "16000", "channels": 1,
        }]}),
        stderr="",
    )
    with patch("engine.ffmpeg.subprocess.run", return_value=fake_completed):
        tracks = probe_audio_tracks(Path("clean.wav"))
    assert tracks[0]["duration_seconds"] is None


from engine.ffmpeg import run_loudnorm_measure


def test_run_loudnorm_measure_parses_json_from_stderr(tmp_path: Path, monkeypatch):
    fake = tmp_path / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    fake.write_bytes(b"")
    monkeypatch.setenv("BWC_CLIPPER_FFMPEG_DIR", str(tmp_path))

    # ffmpeg's loudnorm filter writes a JSON object to stderr after the audio
    # processing summary. Real-world output looks like this:
    fake_stderr = """\
ffmpeg version ... Copyright (c) ...
  built with gcc ...
[Parsed_loudnorm_0 @ 0x...] Loudnorm completed
[Parsed_loudnorm_0 @ 0x...]
{
        "input_i" : "-12.36",
        "input_tp" : "-0.31",
        "input_lra" : "8.20",
        "input_thresh" : "-22.36",
        "output_i" : "-15.12",
        "output_tp" : "-1.50",
        "output_lra" : "9.80",
        "output_thresh" : "-25.12",
        "normalization_type" : "linear",
        "target_offset" : "-1.20"
}
"""
    fake_completed = MagicMock(returncode=0, stdout="", stderr=fake_stderr)
    with patch("engine.ffmpeg.subprocess.run", return_value=fake_completed):
        measured = run_loudnorm_measure(Path("input.wav"))

    assert measured == {
        "input_i": "-12.36",
        "input_tp": "-0.31",
        "input_lra": "8.20",
        "input_thresh": "-22.36",
        "target_offset": "-1.20",
    }


def test_run_loudnorm_measure_raises_on_missing_json(tmp_path: Path, monkeypatch):
    fake = tmp_path / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    fake.write_bytes(b"")
    monkeypatch.setenv("BWC_CLIPPER_FFMPEG_DIR", str(tmp_path))

    fake_completed = MagicMock(returncode=0, stdout="", stderr="ffmpeg version ...\nno json here\n")
    with patch("engine.ffmpeg.subprocess.run", return_value=fake_completed):
        with pytest.raises(RuntimeError, match="loudnorm.*JSON"):
            run_loudnorm_measure(Path("input.wav"))


def test_run_loudnorm_measure_invokes_ffmpeg_with_correct_filter(tmp_path: Path, monkeypatch):
    fake = tmp_path / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    fake.write_bytes(b"")
    monkeypatch.setenv("BWC_CLIPPER_FFMPEG_DIR", str(tmp_path))

    valid_stderr = '{"input_i":"-12","input_tp":"-1","input_lra":"5","input_thresh":"-20","target_offset":"0"}'
    fake_completed = MagicMock(returncode=0, stdout="", stderr=valid_stderr)
    with patch("engine.ffmpeg.subprocess.run", return_value=fake_completed) as run_mock:
        run_loudnorm_measure(Path("input.wav"))

    cmd = run_mock.call_args[0][0]
    af_idx = cmd.index("-af")
    assert "loudnorm=I=-16" in cmd[af_idx + 1]
    assert "LRA=11" in cmd[af_idx + 1]
    assert "TP=-1.5" in cmd[af_idx + 1]
    assert "print_format=json" in cmd[af_idx + 1]
    # measurement pass writes to null sink
    assert "-f" in cmd
    assert "null" in cmd
