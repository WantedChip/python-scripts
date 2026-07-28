"""Unit tests for video_resolution_converter module."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from video_resolution_converter import convert_video_resolution, main  # noqa: E402


def test_convert_video_resolution_missing_ffmpeg() -> None:
    """Test behavior when ffmpeg is missing."""
    with patch("shutil.which", return_value=None):
        res = convert_video_resolution(Path("in.mp4"), Path("out.mp4"))
        assert res is False


@patch("shutil.which", return_value="/usr/bin/ffmpeg")
@patch("subprocess.run")
def test_convert_video_resolution_success(
    mock_run: MagicMock, mock_which: MagicMock, tmp_path: Path
) -> None:
    """Test successful FFmpeg resolution scaling execution."""
    src = tmp_path / "1080p_video.mp4"
    dst = tmp_path / "720p_video.mp4"
    src.write_bytes(b"dummy_video_bytes")

    def mock_subprocess_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        out_file = Path(cmd[-1])
        out_file.write_bytes(b"scaled_bytes")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    mock_run.side_effect = mock_subprocess_run

    ok = convert_video_resolution(src, dst, resolution="720p", crf=20)
    assert ok is True
    assert dst.exists()


@patch("shutil.which", return_value="/usr/bin/ffmpeg")
@patch("subprocess.run")
def test_cli_execution(
    mock_run: MagicMock, mock_which: MagicMock, tmp_path: Path
) -> None:
    """Test CLI batch resolution conversion execution."""
    in_dir = tmp_path / "vids"
    out_dir = tmp_path / "converted"
    in_dir.mkdir()

    vid = in_dir / "sample.mp4"
    vid.write_bytes(b"vid_data")

    def mock_subprocess_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        out_file = Path(cmd[-1])
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_bytes(b"scaled_bytes")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    mock_run.side_effect = mock_subprocess_run

    ret = main([str(in_dir), "-o", str(out_dir), "-r", "480p", "-v"])
    assert ret == 0
    assert (out_dir / "sample_480p.mp4").exists()
