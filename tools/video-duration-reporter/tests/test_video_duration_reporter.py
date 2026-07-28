"""Unit test suite for video_duration_reporter module."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure script directory is on sys.path for pytest
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from video_duration_reporter import (  # noqa: E402
    format_duration,
    get_video_metadata_ffprobe,
    get_video_metadata_native,
    main,
    parse_mp4_duration,
    scan_video_directory,
)


def test_format_duration() -> None:
    """Test duration formatting into HH:MM:SS."""
    assert format_duration(0) == "00:00:00"
    assert format_duration(65) == "00:01:05"
    assert format_duration(3665) == "01:01:05"


def test_get_video_metadata_ffprobe_success(tmp_path: Path) -> None:
    """Test ffprobe metadata extraction when ffprobe succeeds."""
    dummy_video = tmp_path / "sample.mp4"
    dummy_video.write_bytes(b"dummy video data")

    ffprobe_output = {
        "format": {"duration": "12.34", "size": "100"},
        "streams": [
            {
                "codec_type": "video",
                "width": 1920,
                "height": 1080,
                "codec_name": "h264",
            },
            {"codec_type": "audio", "codec_name": "aac"},
        ],
    }

    mock_run = MagicMock()
    mock_run.returncode = 0
    mock_run.stdout = json.dumps(ffprobe_output)

    with (
        patch("shutil.which", return_value="/usr/bin/ffprobe"),
        patch("subprocess.run", return_value=mock_run),
    ):
        meta = get_video_metadata_ffprobe(dummy_video)
        assert meta is not None
        assert meta["duration_seconds"] == 12.34
        assert meta["resolution"] == "1920x1080"
        assert meta["v_codec"] == "h264"
        assert meta["a_codec"] == "aac"


def test_get_video_metadata_ffprobe_fail(tmp_path: Path) -> None:
    """Test ffprobe metadata extraction when ffprobe returns non-zero."""
    dummy_video = tmp_path / "sample.mp4"
    dummy_video.write_bytes(b"dummy video data")
    mock_run = MagicMock()
    mock_run.returncode = 1
    mock_run.stdout = ""

    with (
        patch("shutil.which", return_value="/usr/bin/ffprobe"),
        patch("subprocess.run", return_value=mock_run),
    ):
        assert get_video_metadata_ffprobe(dummy_video) is None


def test_get_video_metadata_native(tmp_path: Path) -> None:
    """Test native fallback video metadata parser."""
    dummy_video = tmp_path / "test.mp4"
    dummy_video.write_bytes(b"dummy mp4 file data")

    meta = get_video_metadata_native(dummy_video)
    assert meta["filename"] == "test.mp4"
    assert meta["size_bytes"] == len(b"dummy mp4 file data")


def test_parse_mp4_duration_valid_v0(tmp_path: Path) -> None:
    """Test mp4 duration parser with valid mvhd v0 structure."""
    header = (
        b"\x00" * 100
        + b"mvhd"
        + b"\x00" * 12
        + (1000).to_bytes(4, "big")
        + (5000).to_bytes(4, "big")
    )
    dummy_file = tmp_path / "mvhd_v0.mp4"
    dummy_file.write_bytes(header)
    assert parse_mp4_duration(dummy_file) == 5.0


def test_parse_mp4_duration_valid_v1(tmp_path: Path) -> None:
    """Test mp4 duration parser with valid mvhd v1 structure."""
    header = (
        b"\x00" * 100
        + b"mvhd"
        + b"\x01\x00\x00\x00"
        + b"\x00" * 16
        + (1000).to_bytes(4, "big")
        + (10000).to_bytes(8, "big")
    )
    dummy_file = tmp_path / "mvhd_v1.mp4"
    dummy_file.write_bytes(header)
    assert parse_mp4_duration(dummy_file) == 10.0


def test_scan_video_directory_and_main(tmp_path: Path) -> None:
    """Test scanning video directory and main CLI execution."""
    v1 = tmp_path / "v1.mp4"
    v1.write_bytes(b"video1")
    v2 = tmp_path / "v2.mkv"
    v2.write_bytes(b"video2")
    txt = tmp_path / "ignore.txt"
    txt.write_text("ignore me")

    results, total_dur = scan_video_directory(tmp_path)
    assert len(results) == 2
    assert total_dur >= 0.0

    csv_out = tmp_path / "out.csv"
    ret = main([str(tmp_path), "-o", str(csv_out), "-f", "json", "-v", "-r"])
    assert ret == 0
    assert csv_out.exists()

    assert main([str(tmp_path), "-f", "table"]) == 0
    assert main([str(tmp_path), "-f", "csv"]) == 0
    assert main([str(tmp_path / "non_existent")]) == 1
