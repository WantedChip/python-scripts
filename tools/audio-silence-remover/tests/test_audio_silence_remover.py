"""Unit tests for audio_silence_remover module."""

import struct
import sys
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure parent directory is on sys.path for direct import
SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

# pylint: disable=wrong-import-position
from audio_silence_remover import (  # noqa: E402
    main,
    remove_audio_silence,
    trim_wav_silence_native,
)


def create_silence_padded_wav(file_path: Path) -> None:
    """Helper to create a WAV file with leading and trailing silence."""
    n_samples = 1000
    # 200 silent, 600 loud, 200 silent
    samples = (
        [0] * 200 + [int(15000 * ((i % 20) / 20.0)) for i in range(600)] + [0] * 200
    )
    packed = struct.pack(f"<{n_samples}h", *samples)

    with wave.open(str(file_path), "wb") as w:
        # pylint: disable=no-member
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(packed)


def test_trim_wav_silence_native(tmp_path: Path) -> None:
    """Test native silence trimming on padded WAV file."""
    src = tmp_path / "padded.wav"
    dst = tmp_path / "trimmed.wav"

    create_silence_padded_wav(src)

    ok = trim_wav_silence_native(src, dst, silence_threshold=100)
    assert ok is True
    assert dst.exists()

    with wave.open(str(dst), "rb") as r:
        n_frames = r.getnframes()
        assert n_frames < 1000  # Trimming removed silent frames


@patch("shutil.which", return_value="/usr/bin/ffmpeg")
def test_remove_audio_silence_ffmpeg(mock_which: MagicMock, tmp_path: Path) -> None:
    """Test silence removal via FFmpeg."""
    src = tmp_path / "test.mp3"
    dst = tmp_path / "out.mp3"
    src.write_bytes(b"dummy")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        dst.write_bytes(b"trimmed_data")

        ok = remove_audio_silence(src, dst)
        assert ok is True


def test_cli_execution(tmp_path: Path) -> None:
    """Test CLI batch silence removal execution."""
    in_dir = tmp_path / "audios"
    out_dir = tmp_path / "out"
    in_dir.mkdir()

    create_silence_padded_wav(in_dir / "sample.wav")

    ret = main([str(in_dir), "-o", str(out_dir), "-v"])
    assert ret == 0
    assert (out_dir / "sample_nosilence.wav").exists()
