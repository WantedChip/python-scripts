"""Unit tests for video_segment_trimmer module."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from video_segment_trimmer import main, trim_video_segment  # noqa: E402


def test_trim_video_missing_ffmpeg() -> None:
    """Test behavior when ffmpeg is not found on PATH."""
    with patch("shutil.which", return_value=None):
        res = trim_video_segment(Path("in.mp4"), Path("out.mp4"))
        assert res is False


@patch("shutil.which", return_value="/usr/bin/ffmpeg")
@patch("subprocess.run")
def test_trim_video_segment_success(
    mock_run: MagicMock, mock_which: MagicMock, tmp_path: Path
) -> None:
    """Test successful FFmpeg video trimming."""
    src = tmp_path / "video.mp4"
    dst = tmp_path / "trimmed.mp4"
    src.write_bytes(b"dummy_video_bytes")

    def mock_subprocess_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        out_file = Path(cmd[-1])
        out_file.write_bytes(b"trimmed_bytes")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    mock_run.side_effect = mock_subprocess_run

    ok = trim_video_segment(src, dst, start_time="00:00:10", end_time="00:00:30")
    assert ok is True
    assert dst.exists()


@patch("shutil.which", return_value="/usr/bin/ffmpeg")
@patch("subprocess.run")
def test_cli_execution(
    mock_run: MagicMock, mock_which: MagicMock, tmp_path: Path
) -> None:
    """Test CLI batch video segment trimming."""
    in_file = tmp_path / "sample.mp4"
    out_dir = tmp_path / "out"
    in_file.write_bytes(b"video_data")

    def mock_subprocess_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        out_file = Path(cmd[-1])
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_bytes(b"trimmed")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    mock_run.side_effect = mock_subprocess_run

    ret = main([str(in_file), "-o", str(out_dir), "-ss", "00:01:00", "-t", "30", "-v"])
    assert ret == 0
    assert (out_dir / "sample_trimmed.mp4").exists()
