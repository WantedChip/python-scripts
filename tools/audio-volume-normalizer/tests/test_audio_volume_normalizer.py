"""Unit tests for audio_volume_normalizer module."""

import struct
import subprocess
import sys
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from audio_volume_normalizer import (  # noqa: E402
    main,
    normalize_audio,
    normalize_wav_file,
)


def create_sample_wav(file_path: Path, amplitude: int = 10000) -> None:
    """Helper to create a valid 16-bit mono WAV file."""
    n_samples = 1000
    samples = [int(amplitude * ((i % 20) / 20.0)) for i in range(n_samples)]
    packed = struct.pack(f"<{n_samples}h", *samples)

    with wave.open(str(file_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(packed)


def test_normalize_wav_file(tmp_path: Path) -> None:
    """Test native peak normalization of 16-bit WAV file."""
    src = tmp_path / "quiet.wav"
    dst = tmp_path / "normalized.wav"

    create_sample_wav(src, amplitude=5000)

    ok = normalize_wav_file(src, dst, target_peak=0.9)
    assert ok is True
    assert dst.exists()

    with wave.open(str(dst), "rb") as r:
        n_frames = r.getnframes()
        data = r.readframes(n_frames)
        samples = list(struct.unpack(f"<{n_frames}h", data))
        max_val = max(abs(s) for s in samples)
        assert max_val > 25000


@patch("shutil.which", return_value="/usr/bin/ffmpeg")
@patch("subprocess.run")
def test_normalize_audio_ffmpeg(
    mock_run: MagicMock, mock_which: MagicMock, tmp_path: Path
) -> None:
    """Test FFmpeg loudnorm audio normalization."""
    src = tmp_path / "song.mp3"
    dst = tmp_path / "norm.mp3"
    src.write_bytes(b"mp3data")

    def mock_subprocess_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        out_file = Path(cmd[-1])
        out_file.write_bytes(b"norm_data")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    mock_run.side_effect = mock_subprocess_run

    ok = normalize_audio(src, dst, target_lufs=-16.0)
    assert ok is True
    assert dst.exists()


def test_cli_execution(tmp_path: Path) -> None:
    """Test CLI audio volume normalization."""
    in_dir = tmp_path / "audios"
    out_dir = tmp_path / "out"
    in_dir.mkdir()

    create_sample_wav(in_dir / "track.wav", amplitude=8000)

    ret = main([str(in_dir), "-o", str(out_dir), "-p", "0.95", "-v"])
    assert ret == 0
    assert (out_dir / "track_norm.wav").exists()
