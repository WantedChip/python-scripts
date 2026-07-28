"""Unit tests for audio_format_converter module."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from audio_format_converter import convert_audio_format, main  # noqa: E402


def test_convert_audio_format_missing_ffmpeg() -> None:
    """Test behavior when ffmpeg is missing."""
    with patch("shutil.which", return_value=None):
        res = convert_audio_format(Path("in.mp3"), Path("out.flac"))
        assert res is False


@patch("shutil.which", return_value="/usr/bin/ffmpeg")
@patch("subprocess.run")
def test_convert_audio_format_success(
    mock_run: MagicMock, mock_which: MagicMock, tmp_path: Path
) -> None:
    """Test successful FFmpeg audio format conversion."""
    src = tmp_path / "song.wav"
    dst = tmp_path / "song.flac"
    src.write_bytes(b"wav_data")

    def mock_subprocess_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        out_file = Path(cmd[-1])
        out_file.write_bytes(b"flac_data")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    mock_run.side_effect = mock_subprocess_run

    ok = convert_audio_format(src, dst, target_format="flac", sample_rate=44100)
    assert ok is True
    assert dst.exists()


@patch("shutil.which", return_value="/usr/bin/ffmpeg")
@patch("subprocess.run")
def test_cli_execution(
    mock_run: MagicMock, mock_which: MagicMock, tmp_path: Path
) -> None:
    """Test CLI batch audio conversion execution."""
    in_dir = tmp_path / "tracks"
    out_dir = tmp_path / "converted"
    in_dir.mkdir()

    vid = in_dir / "track.wav"
    vid.write_bytes(b"wav_bytes")

    def mock_subprocess_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        out_file = Path(cmd[-1])
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_bytes(b"mp3_bytes")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    mock_run.side_effect = mock_subprocess_run

    ret = main([str(in_dir), "-o", str(out_dir), "-f", "mp3", "-v"])
    assert ret == 0
    assert (out_dir / "track.mp3").exists()
