"""Analyzes audio files and reports sections with high noise or clipping.

This module inspects 16-bit PCM WAV audio files (or converts via FFmpeg) to
detect clipped samples (> threshold) and intervals with elevated RMS noise.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import csv
import json
import logging
import math
import shutil
import struct
import subprocess  # nosec B404
import sys
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SUPPORTED_AUDIO_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".flac",
    ".aac",
    ".ogg",
}  # vulture: ignore


def calculate_rms_dbfs(samples: List[int], max_val: int = 32768) -> float:
    """Calculate Root Mean Square (RMS) decibels relative to full scale (dBFS).

    Args:
        samples: List of integer PCM audio samples.
        max_val: Maximum possible sample amplitude value (default: 32768).

    Returns:
        RMS value in dBFS float (e.g. -20.0 dBFS).
    """
    if not samples:
        return -100.0
    sum_squares = sum(s * s for s in samples)
    mean_square = sum_squares / float(len(samples))
    rms = math.sqrt(mean_square)
    if rms <= 0:
        return -100.0
    dbfs = 20.0 * math.log10(rms / float(max_val))
    return max(-100.0, round(dbfs, 2))


def analyze_wav_noise_and_clipping(
    wav_path: Path,
    clip_threshold_ratio: float = 0.99,
    noise_floor_db: float = -30.0,
    window_sec: float = 0.5,
) -> Dict[str, Any]:
    """Analyze a 16-bit PCM WAV file for clipped samples and noisy windows.

    Args:
        wav_path: Path to input WAV file.
        clip_threshold_ratio: Ratio of max PCM amplitude (32767) for clipping.
        noise_floor_db: dBFS threshold above which window noise is flagged.
        window_sec: Window duration in seconds for RMS noise calculation.

    Returns:
        Dictionary containing clipping count, noise sections, and summary metrics.
    """
    clip_limit = int(32767 * clip_threshold_ratio)
    clipped_sample_count = 0
    noisy_windows: List[Dict[str, Any]] = []

    try:
        with wave.open(str(wav_path), "rb") as r_wav:
            n_channels = r_wav.getnchannels()
            samp_width = r_wav.getsampwidth()
            framerate = r_wav.getframerate()
            n_frames = r_wav.getnframes()
            raw_data = r_wav.readframes(n_frames)

        if samp_width != 2 or n_frames == 0 or framerate == 0:
            return {
                "file": str(wav_path),
                "filename": wav_path.name,
                "duration_seconds": 0.0,
                "clipped_samples": 0,
                "clipping_ratio": 0.0,
                "overall_rms_dbfs": -100.0,
                "noisy_sections_count": 0,
                "noisy_windows": [],
                "status": "unsupported_or_empty",
            }

        total_samples = n_frames * n_channels
        fmt = f"<{total_samples}h"
        samples = list(struct.unpack(fmt, raw_data))

        # Count clipped samples
        for s in samples:
            if abs(s) >= clip_limit:
                clipped_sample_count += 1

        clipping_ratio = round(clipped_sample_count / float(total_samples), 6)
        overall_rms = calculate_rms_dbfs(samples)

        # Sliding window analysis for background noise / elevated sections
        window_size_samples = int(framerate * window_sec * n_channels)
        if window_size_samples > 0:
            num_windows = total_samples // window_size_samples
            for idx in range(num_windows):
                w_start = idx * window_size_samples
                w_end = w_start + window_size_samples
                w_samples = samples[w_start:w_end]
                w_rms = calculate_rms_dbfs(w_samples)

                start_sec = round(w_start / (framerate * n_channels), 2)
                end_sec = round(w_end / (framerate * n_channels), 2)

                if w_rms > noise_floor_db:
                    noisy_windows.append(
                        {
                            "start_sec": start_sec,
                            "end_sec": end_sec,
                            "rms_dbfs": w_rms,
                        }
                    )

        duration = round(n_frames / float(framerate), 2)

        return {
            "file": str(wav_path),
            "filename": wav_path.name,
            "duration_seconds": duration,
            "clipped_samples": clipped_sample_count,
            "clipping_ratio": clipping_ratio,
            "overall_rms_dbfs": overall_rms,
            "noisy_sections_count": len(noisy_windows),
            "noisy_windows": noisy_windows,
            "status": "ok",
        }
    except (wave.Error, OSError) as err:
        logger.debug("Error reading WAV file %s: %s", wav_path, err)
        return {
            "file": str(wav_path),
            "filename": wav_path.name,
            "duration_seconds": 0.0,
            "clipped_samples": 0,
            "clipping_ratio": 0.0,
            "overall_rms_dbfs": -100.0,
            "noisy_sections_count": 0,
            "noisy_windows": [],
            "status": f"error: {err}",
        }


def convert_audio_to_temp_wav(audio_path: Path, temp_dir: Path) -> Optional[Path]:
    """Convert non-WAV audio file to temporary 16-bit PCM WAV file via FFmpeg.

    Args:
        audio_path: Path to source non-WAV audio file.
        temp_dir: Directory where temporary WAV will be stored.

    Returns:
        Path to generated temp WAV file, or None if FFmpeg fails.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return None

    temp_wav = temp_dir / f"{audio_path.stem}_temp.wav"
    cmd = [
        ffmpeg_bin,
        "-y",
        "-v",
        "error",
        "-i",
        str(audio_path),
        "-ar",
        "44100",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(temp_wav),
    ]

    try:
        res = subprocess.run(  # nosec B603
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if res.returncode == 0 and temp_wav.exists():
            return temp_wav
    except OSError as err:
        logger.debug("FFmpeg conversion error for %s: %s", audio_path, err)

    return None


def profile_audio_file(
    audio_path: Path,
    temp_dir: Path,
    clip_threshold_ratio: float = 0.99,
    noise_floor_db: float = -30.0,
) -> Dict[str, Any]:
    """Profile an audio file for noise and clipping.

    Args:
        audio_path: Target audio file path.
        temp_dir: Temporary directory for format conversion if needed.
        clip_threshold_ratio: Clipping detection threshold ratio.
        noise_floor_db: Noise floor dBFS threshold.

    Returns:
        Profile report dictionary.
    """
    if audio_path.suffix.lower() == ".wav":
        return analyze_wav_noise_and_clipping(
            audio_path, clip_threshold_ratio, noise_floor_db
        )

    # Convert via FFmpeg if non-WAV format
    temp_wav = convert_audio_to_temp_wav(audio_path, temp_dir)
    if temp_wav:
        res = analyze_wav_noise_and_clipping(
            temp_wav, clip_threshold_ratio, noise_floor_db
        )
        res["file"] = str(audio_path)
        res["filename"] = audio_path.name
        return res

    return {
        "file": str(audio_path),
        "filename": audio_path.name,
        "duration_seconds": 0.0,
        "clipped_samples": 0,
        "clipping_ratio": 0.0,
        "overall_rms_dbfs": -100.0,
        "noisy_sections_count": 0,
        "noisy_windows": [],
        "status": "ffmpeg_required_for_non_wav",
    }


def scan_and_profile_audio(
    target_path: Path,
    temp_dir: Path,
    clip_threshold_ratio: float = 0.99,
    noise_floor_db: float = -30.0,
    recursive: bool = False,
) -> List[Dict[str, Any]]:
    """Scan file or folder of audio files and profile each for noise and clipping.

    Args:
        target_path: Target audio file or directory path.
        temp_dir: Temporary directory for conversion artifacts.
        clip_threshold_ratio: Clipping threshold ratio float.
        noise_floor_db: Decibel noise threshold float.
        recursive: Whether to search subdirectories recursively.

    Returns:
        List of profiling result dictionaries.
    """
    audio_files: List[Path] = []
    if target_path.is_file():
        audio_files.append(target_path)
    elif target_path.is_dir():
        pattern = "**/*" if recursive else "*"
        for item in target_path.glob(pattern):
            if item.is_file() and item.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS:
                audio_files.append(item)

    audio_files.sort(key=lambda p: str(p).lower())

    results: List[Dict[str, Any]] = []
    for a_file in audio_files:
        prof = profile_audio_file(
            a_file, temp_dir, clip_threshold_ratio, noise_floor_db
        )
        results.append(prof)

    return results


def main(args: Optional[List[str]] = None) -> int:
    """Run CLI entry point for audio noise profiler.

    Args:
        args: Command line argument list.

    Returns:
        Exit code integer (0 for success, non-zero for failure).
    """
    parser = argparse.ArgumentParser(
        description="Analyze audio files and report high noise or clipping."
    )
    parser.add_argument("target", type=str, help="Audio file or directory path.")
    parser.add_argument(
        "--clip-threshold",
        type=float,
        default=0.99,
        help="Clipping threshold ratio (0.0 to 1.0, default: 0.99).",
    )
    parser.add_argument(
        "--noise-floor-db",
        type=float,
        default=-30.0,
        help="Noise floor dBFS threshold (default: -30.0).",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Scan directory recursively.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Output report file path.",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["table", "csv", "json"],
        default="table",
        help="Console output format (default: table).",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging."
    )

    parsed_args = parser.parse_args(args)

    level = logging.DEBUG if parsed_args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    target_path = Path(parsed_args.target)
    if not target_path.exists():
        logger.error("Target path does not exist: %s", target_path)
        return 1

    temp_dir = target_path.parent / ".audio_noise_temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        results = scan_and_profile_audio(
            target_path,
            temp_dir,
            parsed_args.clip_threshold,
            parsed_args.noise_floor_db,
            parsed_args.recursive,
        )

        if parsed_args.output:
            out_path = Path(parsed_args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if out_path.suffix.lower() == ".json":
                with open(out_path, "w", encoding="utf-8") as f_out:
                    json.dump(results, f_out, indent=2)
            else:
                fieldnames = [
                    "filename",
                    "duration_seconds",
                    "clipped_samples",
                    "clipping_ratio",
                    "overall_rms_dbfs",
                    "noisy_sections_count",
                    "status",
                    "file",
                ]
                with open(out_path, "w", newline="", encoding="utf-8") as f_csv:
                    writer = csv.DictWriter(
                        f_csv, fieldnames=fieldnames, extrasaction="ignore"
                    )
                    writer.writeheader()
                    writer.writerows(results)
            logger.info("Report exported to %s", out_path)

        if parsed_args.format == "json":
            print(json.dumps(results, indent=2))
        elif parsed_args.format == "csv":
            fieldnames = [
                "filename",
                "duration_seconds",
                "clipped_samples",
                "clipping_ratio",
                "overall_rms_dbfs",
                "noisy_sections_count",
            ]
            writer = csv.DictWriter(
                sys.stdout, fieldnames=fieldnames, extrasaction="ignore"
            )
            writer.writeheader()
            writer.writerows(results)
        else:  # table
            print(f"\nAudio Noise & Clipping Report ({len(results)} files)")
            print("-" * 75)
            hdr = (
                f"{'Filename':<25} | {'Clipped':<8} | {'RMS (dBFS)':<10} | "
                f"{'Noisy Sec':<9} | {'Status':<12}"
            )
            print(hdr)
            print("-" * 75)
            for item in results:
                fname = (
                    item["filename"][:22] + "..."
                    if len(item["filename"]) > 25
                    else item["filename"]
                )
                print(
                    f"{fname:<25} | {item['clipped_samples']:<8} | "
                    f"{item['overall_rms_dbfs']:<10} | "
                    f"{item['noisy_sections_count']:<9} | {item['status']:<12}"
                )
            print("-" * 75 + "\n")

        return 0
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
