"""Remove leading, trailing, or internal silence intervals from audio files.

This module trims silent portions of audio using native WAV PCM sample analysis or
FFmpeg silenceremove filter bindings for compressed audio files.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments

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


def trim_wav_silence_native(
    input_wav: Path,
    output_wav: Path,
    silence_threshold: int = 500,
) -> bool:
    """Trim leading and trailing silence from a 16-bit PCM WAV file natively.

    Args:
        input_wav: Path to source WAV audio file.
        output_wav: Path to output trimmed WAV file.
        silence_threshold: Absolute sample amplitude threshold below which is silence.

    Returns:
        True if trimming succeeded, False otherwise.
    """
    try:
        with wave.open(str(input_wav), "rb") as r_wav:
            n_channels = r_wav.getnchannels()
            samp_width = r_wav.getsampwidth()
            framerate = r_wav.getframerate()
            n_frames = r_wav.getnframes()
            raw_data = r_wav.readframes(n_frames)

        if samp_width != 2 or n_frames == 0:
            return False

        fmt = f"<{n_frames * n_channels}h"
        samples = list(struct.unpack(fmt, raw_data))

        # Determine non-silent frame indices
        start_idx = 0
        end_idx = len(samples) - 1

        while start_idx < len(samples) and abs(samples[start_idx]) <= silence_threshold:
            start_idx += 1

        while end_idx > start_idx and abs(samples[end_idx]) <= silence_threshold:
            end_idx -= 1

        # Align to frame boundaries (channels)
        start_frame = (start_idx // n_channels) * n_channels
        end_frame = ((end_idx // n_channels) + 1) * n_channels

        trimmed_samples = samples[start_frame:end_frame]
        if not trimmed_samples:
            logger.warning(
                "Entire audio file is below silence threshold: %s",
                input_wav,
            )
            return False

        trimmed_fmt = f"<{len(trimmed_samples)}h"
        packed_data = struct.pack(trimmed_fmt, *trimmed_samples)

        output_wav.parent.mkdir(parents=True, exist_ok=True)
        # pylint: disable=no-member
        with wave.open(str(output_wav), "wb") as w_wav:
            w_wav.setnchannels(n_channels)
            w_wav.setsampwidth(samp_width)
            w_wav.setframerate(framerate)
            w_wav.writeframes(packed_data)

        logger.info(
            "Natively trimmed silence: %s -> %s",
            input_wav.name,
            output_wav.name,
        )
        return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed native WAV silence trimming for %s: %s", input_wav, exc)
        return False


def remove_silence_ffmpeg(
    input_file: Path,
    output_file: Path,
    threshold_db: str = "-50dB",
    overwrite: bool = True,
) -> bool:
    """Remove silence from audio using FFmpeg silenceremove filter.

    Args:
        input_file: Input audio file path.
        output_file: Target trimmed output audio file path.
        threshold_db: Silence decibel threshold (default: '-50dB').
        overwrite: Overwrite destination file if True.

    Returns:
        True if FFmpeg silence removal succeeded, False otherwise.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return False

    output_file.parent.mkdir(parents=True, exist_ok=True)
    filter_spec = (
        f"silenceremove=start_periods=1:start_duration=0.1:"
        f"start_threshold={threshold_db}:stop_periods=1:"
        f"stop_duration=0.1:stop_threshold={threshold_db}"
    )

    cmd = [
        ffmpeg_bin,
        "-y" if overwrite else "-n",
        "-i",
        str(input_file),
        "-af",
        filter_spec,
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
                "Removed silence with FFmpeg: %s -> %s",
                input_file.name,
                output_file.name,
            )
            return True

        logger.error("FFmpeg silence removal error: %s", res.stderr)
        return False
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Exception running FFmpeg silence removal: %s", exc)
        return False


def remove_audio_silence(
    input_file: Path,
    output_file: Path,
    threshold_db: str = "-50dB",
) -> bool:
    """Remove silence from audio using FFmpeg or native WAV fallback.

    Args:
        input_file: Input audio file path.
        output_file: Target trimmed output audio file path.
        threshold_db: Silence threshold decibels.

    Returns:
        True if silence removed successfully, False otherwise.
    """
    if shutil.which("ffmpeg"):
        ok = remove_silence_ffmpeg(input_file, output_file, threshold_db=threshold_db)
        if ok:
            return True

    if input_file.suffix.lower() == ".wav":
        return trim_wav_silence_native(input_file, output_file)

    logger.error("Cannot process %s: FFmpeg is missing.", input_file)
    return False


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description="Remove leading, trailing, or internal silence from audio files."
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
        "-t",
        "--threshold",
        default="-50dB",
        help="Silence threshold in dB for FFmpeg (default: '-50dB').",
    )
    parser.add_argument(
        "--suffix",
        type=str,
        default="_nosilence",
        help="Filename suffix for output files (default: '_nosilence').",
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

        ok = remove_audio_silence(
            src,
            dst,
            threshold_db=parsed_args.threshold,
        )
        if ok:
            success_cnt += 1

    logger.info(
        "Successfully removed silence from %d/%d audio files.",
        success_cnt,
        len(audio_files),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
