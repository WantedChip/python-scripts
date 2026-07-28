"""Unit tests for podcast_audio_splitter module."""

import struct
import sys
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from podcast_audio_splitter import (  # noqa: E402
    detect_silence_timestamps_ffmpeg,
    main,
    split_audio_podcast,
    split_wav_silence_native,
)


def create_multi_chapter_wav(file_path: Path) -> None:
    """Helper to create a WAV file with silence intervals between speech chapters."""
    framerate = 44100
    ch1 = [int(15000 * ((i % 20) / 20.0)) for i in range(framerate * 2)]
    silence = [0] * (framerate * 2)
    ch2 = [int(15000 * ((i % 20) / 20.0)) for i in range(framerate * 2)]

    samples = ch1 + silence + ch2
    packed = struct.pack(f"<{len(samples)}h", *samples)

    with wave.open(str(file_path), "wb") as w:
        # pylint: disable=no-member
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)
        w.writeframes(packed)


def test_split_wav_silence_native(tmp_path: Path) -> None:
    """Test native WAV podcast silence splitting."""
    src = tmp_path / "podcast.wav"
    out_dir = tmp_path / "chapters"

    create_multi_chapter_wav(src)

    chapters = split_wav_silence_native(src, out_dir, min_silence_sec=1.0)
    assert len(chapters) == 2
    assert (out_dir / "chapter_01.wav").exists()
    assert (out_dir / "chapter_02.wav").exists()


@patch("shutil.which", return_value="/usr/bin/ffmpeg")
def test_detect_silence_timestamps_ffmpeg(
    mock_which: MagicMock, tmp_path: Path
) -> None:
    """Test silence timestamp parsing from FFmpeg output."""
    src = tmp_path / "episode.mp3"
    src.write_bytes(b"mp3_data")

    fake_stderr = (
        "[silencedetect @ 0x12345] silence_start: 100.5\n"
        "[silencedetect @ 0x12345] silence_end: 104.5\n"
    )

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr=fake_stderr)
        ts = detect_silence_timestamps_ffmpeg(src, min_silence_sec=1.5)
        assert ts == [102.5]


@patch("shutil.which", return_value="/usr/bin/ffmpeg")
def test_split_audio_podcast_ffmpeg(mock_which: MagicMock, tmp_path: Path) -> None:
    """Test FFmpeg podcast audio chapter splitting."""
    src = tmp_path / "episode.mp3"
    out_dir = tmp_path / "mp3_chapters"
    src.write_bytes(b"mp3_data")

    with patch(
        "podcast_audio_splitter.detect_silence_timestamps_ffmpeg"
    ) as mock_detect:
        mock_detect.return_value = [120.5, 340.0]

        def mock_subprocess_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            (out_dir / "chapter_01.mp3").write_bytes(b"ch1")
            (out_dir / "chapter_02.mp3").write_bytes(b"ch2")
            return MagicMock(returncode=0, stderr="")

        with patch("subprocess.run", side_effect=mock_subprocess_run):
            chapters = split_audio_podcast(src, out_dir, min_silence_sec=1.5)
            assert len(chapters) == 2


def test_cli_execution(tmp_path: Path) -> None:
    """Test CLI podcast splitter execution."""
    src = tmp_path / "show.wav"
    out_dir = tmp_path / "show_chapters"
    create_multi_chapter_wav(src)

    ret = main([str(src), "-o", str(out_dir), "-s", "1.0", "-v"])
    assert ret == 0
    assert (out_dir / "chapter_01.wav").exists()
