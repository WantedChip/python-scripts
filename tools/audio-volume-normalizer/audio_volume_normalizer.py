"""Normalize audio file volume levels to target peak or LUFS/RMS loudness levels.

This module normalizes audio files (WAV natively, or MP3/AAC via FFmpeg) to a specified
target peak fraction (0.0 to 1.0) or dB level for consistent listening volume.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments,no-member

import argparse
import logging
import os
import shutil
import struct
import subprocess  # nosec B404
import sys
import wave
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".aac", ".ogg"}


def normalize_wav_file(
    input_wav: Path,
    output_wav: Path,
    target_peak: float = 0.95,
) -> bool:
    """Normalize a uncompressed PCM WAV file natively.

    Args:
        input_wav: Path to source WAV audio file.
        output_wav: Path to output normalized WAV file.
        target_peak: Target peak amplitude scale factor (0.0 to 1.0).

    Returns:
        True if WAV normalization succeeded, False otherwise.
    """
    try:
        with wave.open(str(input_wav), "rb") as r_wav:
            n_channels = r_wav.getnchannels()
            samp_width = r_wav.getsampwidth()
            framerate = r_wav.getframerate()
            n_frames = r_wav.getnframes()
            raw_data = r_wav.readframes(n_frames)

        if samp_width != 2:
            logger.warning("Native normalization requires 16-bit PCM WAV.")
            return False

        # Unpack 16-bit signed integer samples
        fmt = f"<{n_frames * n_channels}h"
        samples = list(struct.unpack(fmt, raw_data))

        if not samples:
            return False

        max_sample = max(abs(s) for s in samples)
        if max_sample == 0:
            logger.warning("Silent audio file: %s", input_wav)
            return False

        scale = (target_peak * 32767.0) / max_sample
        scaled_samples = [max(-32768, min(32767, int(s * scale))) for s in samples]

        packed_data = struct.pack(fmt, *scaled_samples)

        output_wav.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_wav), "wb") as w_wav:
            w_wav.setnchannels(n_channels)
            w_wav.setsampwidth(samp_width)
            w_wav.setframerate(framerate)
            w_wav.writeframes(packed_data)

            logger.info(
                "Natively normalized WAV: %s -> %s",
                input_wav.name,
                output_wav.name,
            )
        return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed native WAV normalization for %s: %s", input_wav, exc)
        return False


def normalize_audio_ffmpeg(
    input_file: Path,
    output_file: Path,
    target_lufs: float = -14.0,
    overwrite: bool = True,
) -> bool:
    """Normalize audio level using FFmpeg loudnorm audio filter.

    Args:
        input_file: Path to source audio file.
        output_file: Path to output normalized audio file.
        target_lufs: Target integrated loudness level in LUFS (default: -14.0).
        overwrite: Overwrite destination file if True.

    Returns:
        True if FFmpeg loudness normalization succeeded, False otherwise.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return False

    output_file.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_bin,
        "-y" if overwrite else "-n",
        "-i",
        str(input_file),
        "-af",
        f"loudnorm=I={target_lufs}:LRA=11:TP=-1.5",
        str(output_file),
    ]

    try:
        res = subprocess.run(  # nosec B603
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )
        if res.returncode == 0 and output_file.exists():
            logger.info(
                "Normalized audio with FFmpeg: %s -> %s",
                input_file.name,
                output_file.name,
            )
            return True

        logger.error("FFmpeg loudnorm error: %s", res.stderr)
        return False
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Exception running FFmpeg loudnorm: %s", exc)
        return False


def normalize_audio(
    input_file: Path,
    output_file: Path,
    target_peak: float = 0.95,
    target_lufs: float = -14.0,
) -> bool:
    """Normalize an audio file using native WAV engine or FFmpeg fallback.

    Args:
        input_file: Input audio file path.
        output_file: Target normalized audio file path.
        target_peak: Native WAV target peak scale factor (0.0 to 1.0).
        target_lufs: FFmpeg target LUFS loudness level.

    Returns:
        True if normalized successfully, False otherwise.
    """
    # 1. Try FFmpeg if installed
    if shutil.which("ffmpeg"):
        ok = normalize_audio_ffmpeg(input_file, output_file, target_lufs=target_lufs)
        if ok:
            return True

    # 2. Native fallback for 16-bit WAV files
    if input_file.suffix.lower() == ".wav":
        return normalize_wav_file(input_file, output_file, target_peak=target_peak)

    logger.error("Cannot normalize %s: FFmpeg missing.", input_file)
    return False


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description="Normalize audio volume levels to standard LUFS or peak targets."
    )
    parser.add_argument(
        "input",
        type=str,
        help="Input audio file or directory path.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Output directory path. Defaults to input location.",
    )
    parser.add_argument(
        "-l",
        "--lufs",
        type=float,
        default=-14.0,
        help="Target integrated loudness LUFS for FFmpeg (default: -14.0).",
    )
    parser.add_argument(
        "-p",
        "--peak",
        type=float,
        default=0.95,
        help="Target peak scale fraction for native WAV mode (default: 0.95).",
    )
    parser.add_argument(
        "--suffix",
        type=str,
        default="_norm",
        help="Filename suffix for normalized files (default: '_norm').",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable detailed debug logging.",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI entry point.

    Args:
        args: Argument list or None for sys.argv[1:].

    Returns:
        Exit code integer (0 for success, non-zero for error).
    """
    parser = setup_cli_parser()
    parsed_args = parser.parse_args(args)

    log_level = logging.DEBUG if parsed_args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    input_path = Path(parsed_args.input)
    if not input_path.exists():
        logger.error("Input path does not exist: %s", input_path)
        return 1

    audio_files: List[Path] = []
    if input_path.is_file():
        audio_files.append(input_path)
    elif input_path.is_dir():
        for root, _, filenames in os.walk(input_path):
            for fname in filenames:
                p = Path(root) / fname
                if p.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS:
                    audio_files.append(p)

    if not audio_files:
        logger.warning("No supported audio files found to process.")
        return 0

    out_dir = Path(parsed_args.output) if parsed_args.output else input_path.parent
    if input_path.is_dir() and not parsed_args.output:
        out_dir = input_path

    success_cnt = 0
    for src in audio_files:
        rel = src.relative_to(input_path) if input_path.is_dir() else Path(src.name)
        dst = out_dir / rel.parent / f"{rel.stem}{parsed_args.suffix}{rel.suffix}"

        ok = normalize_audio(
            src,
            dst,
            target_peak=parsed_args.peak,
            target_lufs=parsed_args.lufs,
        )
        if ok:
            success_cnt += 1

    logger.info(
        "Successfully normalized %d/%d audio files.",
        success_cnt,
        len(audio_files),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
