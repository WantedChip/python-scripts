"""Unit test suite for video_concatenator module."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure script directory is on sys.path for pytest
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from video_concatenator import (  # noqa: E402
    concatenate_videos_ffmpeg,
    load_clip_list_from_config,
    main,
)


def test_load_clip_list_json(tmp_path: Path) -> None:
    """Test parsing clip list from JSON config file."""
    c1 = tmp_path / "clip1.mp4"
    c2 = tmp_path / "clip2.mp4"
    c1.touch()
    c2.touch()

    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps(["clip1.mp4", "clip2.mp4"]))

    clips = load_clip_list_from_config(cfg)
    assert len(clips) == 2
    assert clips[0] == c1
    assert clips[1] == c2


def test_load_clip_list_txt(tmp_path: Path) -> None:
    """Test parsing clip list from TXT config file."""
    c1 = tmp_path / "clipA.mp4"
    c1.touch()

    cfg = tmp_path / "config.txt"
    cfg.write_text("# Comment line\nclipA.mp4\n")

    clips = load_clip_list_from_config(cfg)
    assert len(clips) == 1
    assert clips[0] == c1


def test_concatenate_videos_ffmpeg_success(tmp_path: Path) -> None:
    """Test FFmpeg concatenation when FFmpeg succeeds."""
    c1 = tmp_path / "c1.mp4"
    c2 = tmp_path / "c2.mp4"
    c1.touch()
    c2.touch()
    out = tmp_path / "out.mp4"

    mock_run = MagicMock()
    mock_run.returncode = 0

    def mock_run_side_effect(*args: MagicMock, **kwargs: MagicMock) -> MagicMock:
        out.touch()
        return mock_run

    with (
        patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        patch("subprocess.run", side_effect=mock_run_side_effect),
    ):
        res = concatenate_videos_ffmpeg([c1, c2], out, reencode=True)
        assert res is True
        assert out.exists()


def test_concatenate_videos_ffmpeg_no_binary(tmp_path: Path) -> None:
    """Test FFmpeg concatenation when FFmpeg is not found."""
    c1 = tmp_path / "c1.mp4"
    out = tmp_path / "out.mp4"

    with patch("shutil.which", return_value=None):
        assert concatenate_videos_ffmpeg([c1], out) is False


def test_main_cli_success(tmp_path: Path) -> None:
    """Test main CLI entrypoint execution."""
    c1 = tmp_path / "c1.mp4"
    c2 = tmp_path / "c2.mp4"
    c1.touch()
    c2.touch()
    out = tmp_path / "out.mp4"

    with patch("video_concatenator.concatenate_videos_ffmpeg", return_value=True):
        ret = main(
            [
                "-f",
                str(c1),
                str(c2),
                "-o",
                str(out),
                "-v",
                "--reencode",
            ]
        )
        assert ret == 0


def test_main_cli_validation_failures(tmp_path: Path) -> None:
    """Test CLI error handling for missing files and missing arguments."""
    assert main([]) == 1
    assert main(["-c", str(tmp_path / "non_existent.json")]) == 1
    assert main(["-f", str(tmp_path / "missing.mp4")]) == 1
