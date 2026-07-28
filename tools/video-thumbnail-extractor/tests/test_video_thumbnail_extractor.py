"""Unit tests for video_thumbnail_extractor module."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from video_thumbnail_extractor import extract_video_thumbnail, main  # noqa: E402


def test_extract_thumbnail_missing_ffmpeg() -> None:
    """Test behavior when ffmpeg is missing."""
    with patch("shutil.which", return_value=None):
        res = extract_video_thumbnail(Path("in.mp4"), Path("out.jpg"))
        assert res is False


@patch("shutil.which", return_value="/usr/bin/ffmpeg")
@patch("subprocess.run")
def test_extract_video_thumbnail_success(
    mock_run: MagicMock, mock_which: MagicMock, tmp_path: Path
) -> None:
    """Test successful video thumbnail frame extraction."""
    src = tmp_path / "video.mp4"
    dst = tmp_path / "thumb.png"
    src.write_bytes(b"dummy_video_bytes")

    def mock_subprocess_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        out_file = Path(cmd[-1])
        out_file.write_bytes(b"png_image_bytes")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    mock_run.side_effect = mock_subprocess_run

    ok = extract_video_thumbnail(src, dst, timestamp="00:00:05", scale_width=640)
    assert ok is True
    assert dst.exists()


@patch("shutil.which", return_value="/usr/bin/ffmpeg")
@patch("subprocess.run")
def test_cli_execution(
    mock_run: MagicMock, mock_which: MagicMock, tmp_path: Path
) -> None:
    """Test CLI thumbnail extraction execution."""
    in_dir = tmp_path / "vids"
    out_dir = tmp_path / "thumbs"
    in_dir.mkdir()

    vid = in_dir / "clip.mp4"
    vid.write_bytes(b"video_bytes")

    def mock_subprocess_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        out_file = Path(cmd[-1])
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_bytes(b"jpg_bytes")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    mock_run.side_effect = mock_subprocess_run

    ret = main([str(in_dir), "-o", str(out_dir), "-ss", "00:00:02", "-f", "jpg", "-v"])
    assert ret == 0
    assert (out_dir / "clip_thumb.jpg").exists()
