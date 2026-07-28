"""Unit tests for video_to_audio_extractor module."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from video_to_audio_extractor import extract_audio, main  # noqa: E402


def test_extract_audio_missing_ffmpeg() -> None:
    """Test behavior when ffmpeg is not found on PATH."""
    with patch("shutil.which", return_value=None):
        res = extract_audio(Path("input.mp4"), Path("output.mp3"))
        assert res is False


@patch("shutil.which", return_value="/usr/bin/ffmpeg")
@patch("subprocess.run")
def test_extract_audio_mp3_and_wav(
    mock_run: MagicMock, mock_which: MagicMock, tmp_path: Path
) -> None:
    """Test successful FFmpeg audio extraction for MP3 and WAV."""
    src = tmp_path / "video.mp4"
    dst_mp3 = tmp_path / "audio.mp3"
    dst_wav = tmp_path / "audio.wav"
    src.write_bytes(b"dummy_video")

    def mock_subprocess_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        out_file = Path(cmd[-1])
        out_file.write_bytes(b"audio_bytes")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    mock_run.side_effect = mock_subprocess_run

    ok1 = extract_audio(src, dst_mp3, audio_format="mp3")
    assert ok1 is True
    assert dst_mp3.exists()

    ok2 = extract_audio(src, dst_wav, audio_format="wav")
    assert ok2 is True
    assert dst_wav.exists()


@patch("shutil.which", return_value="/usr/bin/ffmpeg")
@patch("subprocess.run")
def test_cli_directory_batch(
    mock_run: MagicMock, mock_which: MagicMock, tmp_path: Path
) -> None:
    """Test CLI batch directory processing."""
    in_dir = tmp_path / "vids"
    out_dir = tmp_path / "audios"
    in_dir.mkdir()

    vid = in_dir / "test.mp4"
    vid.write_bytes(b"dummy_vid_content")

    def mock_subprocess_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        out_file = Path(cmd[-1])
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_bytes(b"audio_bytes")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    mock_run.side_effect = mock_subprocess_run

    ret = main([str(in_dir), "-o", str(out_dir), "-f", "aac", "-v"])
    assert ret == 0
    assert (out_dir / "test.aac").exists()


@patch("shutil.which", return_value="/usr/bin/ffmpeg")
def test_cli_missing_input(mock_which: MagicMock) -> None:
    """Test CLI exit code when input file does not exist."""
    ret = main(["non_existent_file.mp4"])
    assert ret == 1
