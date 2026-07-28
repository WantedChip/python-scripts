"""Unit test suite for audio_noise_profiler module."""

import struct
import sys
import wave
from pathlib import Path

# Ensure script directory is on sys.path for pytest
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from audio_noise_profiler import (  # noqa: E402
    analyze_wav_noise_and_clipping,
    calculate_rms_dbfs,
    main,
    profile_audio_file,
    scan_and_profile_audio,
)


def create_test_wav(
    file_path: Path,
    samples: list[int],
    framerate: int = 44100,
) -> None:
    """Helper to generate 16-bit mono WAV test file."""
    # pylint: disable=no-member
    with wave.open(str(file_path), "wb") as w_file:
        w_file.setnchannels(1)
        w_file.setsampwidth(2)
        w_file.setframerate(framerate)
        data = struct.pack(f"<{len(samples)}h", *samples)
        w_file.writeframes(data)


def test_calculate_rms_dbfs() -> None:
    """Test RMS dBFS calculation."""
    assert calculate_rms_dbfs([]) == -100.0
    assert calculate_rms_dbfs([0, 0, 0]) == -100.0
    max_samples = [32767, -32767, 32767]
    rms = calculate_rms_dbfs(max_samples)
    assert -1.0 <= rms <= 0.0


def test_analyze_wav_noise_and_clipping(tmp_path: Path) -> None:
    """Test Wav analysis for clipping and noisy windows."""
    wav_file = tmp_path / "test_clip.wav"
    # Create 1 second of samples with some clipped samples (>32440)
    samples = [1000] * 20000 + [32767] * 100 + [-32767] * 100
    create_test_wav(wav_file, samples, framerate=22050)

    res = analyze_wav_noise_and_clipping(
        wav_file, clip_threshold_ratio=0.99, noise_floor_db=-40.0
    )

    assert res["status"] == "ok"
    assert res["clipped_samples"] == 200
    assert res["duration_seconds"] > 0
    assert res["noisy_sections_count"] > 0


def test_profile_non_wav_without_ffmpeg(tmp_path: Path) -> None:
    """Test profiling non-WAV audio file when ffmpeg is missing."""
    mp3_file = tmp_path / "test.mp3"
    mp3_file.write_bytes(b"fake mp3 content")

    res = profile_audio_file(mp3_file, tmp_path)
    assert res["filename"] == "test.mp3"


def test_scan_and_profile_audio_and_main(tmp_path: Path) -> None:
    """Test folder scanning and main CLI invocation."""
    wav1 = tmp_path / "sound1.wav"
    wav2 = tmp_path / "sound2.wav"
    create_test_wav(wav1, [500] * 1000)
    create_test_wav(wav2, [32767] * 50)

    results = scan_and_profile_audio(tmp_path, tmp_path)
    assert len(results) == 2

    out_json = tmp_path / "report.json"
    assert main([str(tmp_path), "-o", str(out_json), "-f", "json"]) == 0
    assert out_json.exists()

    out_csv = tmp_path / "report.csv"
    assert main([str(tmp_path), "-o", str(out_csv), "-f", "csv"]) == 0
    assert out_csv.exists()

    assert main([str(tmp_path), "-f", "table"]) == 0
    assert main([str(tmp_path / "non_existent")]) == 1
