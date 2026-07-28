"""Unit tests for audio_file_joiner module."""

import struct
import sys
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from audio_file_joiner import (  # noqa: E402
    join_audio_files,
    join_wav_files_native,
    main,
)


def create_sample_wav(file_path: Path, n_samples: int = 500) -> None:
    """Helper to create a 16-bit PCM mono WAV file."""
    samples = [int(10000 * ((i % 20) / 20.0)) for i in range(n_samples)]
    packed = struct.pack(f"<{n_samples}h", *samples)

    with wave.open(str(file_path), "wb") as w:
        # pylint: disable=no-member
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(packed)


def test_join_wav_files_native(tmp_path: Path) -> None:
    """Test native WAV concatenation."""
    w1 = tmp_path / "part1.wav"
    w2 = tmp_path / "part2.wav"
    out = tmp_path / "merged.wav"

    create_sample_wav(w1, 500)
    create_sample_wav(w2, 500)

    ok = join_wav_files_native([w1, w2], out)
    assert ok is True
    assert out.exists()

    with wave.open(str(out), "rb") as r:
        assert r.getnframes() == 1000


@patch("shutil.which", return_value="/usr/bin/ffmpeg")
def test_join_audio_files_ffmpeg(mock_which: MagicMock, tmp_path: Path) -> None:
    """Test FFmpeg audio file concatenation."""
    a1 = tmp_path / "file1.mp3"
    a2 = tmp_path / "file2.mp3"
    out = tmp_path / "output.mp3"
    a1.write_bytes(b"data1")
    a2.write_bytes(b"data2")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        out.write_bytes(b"merged_mp3_data")

        ok = join_audio_files([a1, a2], out)
        assert ok is True
        assert out.exists()


def test_cli_execution(tmp_path: Path) -> None:
    """Test CLI joiner command execution."""
    w1 = tmp_path / "1.wav"
    w2 = tmp_path / "2.wav"
    out = tmp_path / "combined.wav"
    create_sample_wav(w1, 200)
    create_sample_wav(w2, 300)

    ret = main([str(w1), str(w2), "-o", str(out), "-v"])
    assert ret == 0
    assert out.exists()
