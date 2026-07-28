"""Unit tests for video_speed_changer module."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from video_speed_changer import (  # noqa: E402
    build_atempo_filter,
    change_video_speed,
    main,
)


def test_build_atempo_filter() -> None:
    """Test building atempo filter string for various speed factors."""
    assert build_atempo_filter(1.5) == "atempo=1.5000"
    assert build_atempo_filter(2.0) == "atempo=2.0000"
    assert "atempo=2.0" in build_atempo_filter(4.0)
    assert "atempo=0.5" in build_atempo_filter(0.25)


def test_change_video_speed_missing_ffmpeg() -> None:
    """Test behavior when ffmpeg is missing."""
    with patch("shutil.which", return_value=None):
        res = change_video_speed(Path("in.mp4"), Path("out.mp4"))
        assert res is False


@patch("shutil.which", return_value="/usr/bin/ffmpeg")
@patch("subprocess.run")
def test_change_video_speed_success(
    mock_run: MagicMock, mock_which: MagicMock, tmp_path: Path
) -> None:
    """Test successful video speed adjustment."""
    src = tmp_path / "normal.mp4"
    dst = tmp_path / "fast.mp4"
    src.write_bytes(b"dummy_video_bytes")

    def mock_subprocess_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        out_file = Path(cmd[-1])
        out_file.write_bytes(b"fast_bytes")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    mock_run.side_effect = mock_subprocess_run

    ok = change_video_speed(src, dst, speed=2.0)
    assert ok is True
    assert dst.exists()


@patch("shutil.which", return_value="/usr/bin/ffmpeg")
@patch("subprocess.run")
def test_cli_execution(
    mock_run: MagicMock, mock_which: MagicMock, tmp_path: Path
) -> None:
    """Test CLI video speed changer execution."""
    in_dir = tmp_path / "vids"
    out_dir = tmp_path / "out"
    in_dir.mkdir()

    vid = in_dir / "clip.mp4"
    vid.write_bytes(b"vid_data")

    def mock_subprocess_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        out_file = Path(cmd[-1])
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_bytes(b"speed_data")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    mock_run.side_effect = mock_subprocess_run

    ret = main([str(in_dir), "-o", str(out_dir), "-s", "1.5", "-v"])
    assert ret == 0
    assert (out_dir / "clip_1.5x.mp4").exists()
