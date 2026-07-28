"""Unit tests for video_watermarker module."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from video_watermarker import (  # noqa: E402
    add_image_watermark,
    add_text_watermark,
    main,
)


def test_watermark_missing_ffmpeg() -> None:
    """Test behavior when ffmpeg is missing."""
    with patch("shutil.which", return_value=None):
        res = add_text_watermark(Path("in.mp4"), "test", Path("out.mp4"))
        assert res is False


@patch("shutil.which", return_value="/usr/bin/ffmpeg")
@patch("subprocess.run")
def test_add_image_watermark_success(
    mock_run: MagicMock, mock_which: MagicMock, tmp_path: Path
) -> None:
    """Test successful image logo watermarking."""
    src = tmp_path / "video.mp4"
    logo = tmp_path / "logo.png"
    dst = tmp_path / "watermarked.mp4"
    src.write_bytes(b"video_bytes")
    logo.write_bytes(b"logo_bytes")

    def mock_subprocess_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        out_file = Path(cmd[-1])
        out_file.write_bytes(b"wm_video_bytes")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    mock_run.side_effect = mock_subprocess_run

    ok = add_image_watermark(src, logo, dst, position="bottom-right")
    assert ok is True
    assert dst.exists()


@patch("shutil.which", return_value="/usr/bin/ffmpeg")
@patch("subprocess.run")
def test_cli_text_watermark(
    mock_run: MagicMock, mock_which: MagicMock, tmp_path: Path
) -> None:
    """Test CLI text watermarking execution."""
    in_dir = tmp_path / "vids"
    out_dir = tmp_path / "wm_out"
    in_dir.mkdir()

    vid = in_dir / "clip.mp4"
    vid.write_bytes(b"vid_data")

    def mock_subprocess_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        out_file = Path(cmd[-1])
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_bytes(b"wm_data")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    mock_run.side_effect = mock_subprocess_run

    ret = main(
        [
            str(in_dir),
            "-o",
            str(out_dir),
            "-t",
            "Copyright 2026",
            "-p",
            "top-left",
            "-v",
        ]
    )
    assert ret == 0
    assert (out_dir / "clip_wm.mp4").exists()
