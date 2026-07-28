"""Split long audio files or podcast episodes into chapters using silence detection.

This module detects silence boundaries (minimum duration and dB threshold) to segment
audio recordings into sequential chapter files natively for WAV or via FFmpeg.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import logging
import re
import shutil
import struct
import subprocess  # nosec B404
import sys
import wave
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

SUPPORTED_AUDIO_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".flac",
    ".aac",
    ".ogg",
}  # vulture: ignore


def split_wav_silence_native(
    input_wav: Path,
    output_dir: Path,
    min_silence_sec: float = 1.5,
    silence_threshold: int = 400,
    prefix: str = "chapter_",
) -> List[Path]:
    """Split 16-bit PCM WAV audio file into chapters using native silence detection.

    Args:
        input_wav: Path to source WAV audio file.
        output_dir: Directory where chapter files will be written.
        min_silence_sec: Minimum duration of silence in seconds to trigger split.
        silence_threshold: Maximum sample amplitude considered silence.
        prefix: Filename prefix for output chapters.

    Returns:
        List of generated chapter output file paths.
    """
    chapter_files: List[Path] = []
    try:
        with wave.open(str(input_wav), "rb") as r_wav:
            n_channels = r_wav.getnchannels()
            samp_width = r_wav.getsampwidth()
            framerate = r_wav.getframerate()
            n_frames = r_wav.getnframes()
            raw_data = r_wav.readframes(n_frames)

        if samp_width != 2 or n_frames == 0:
            return chapter_files

        fmt = f"<{n_frames * n_channels}h"
        samples = list(struct.unpack(fmt, raw_data))

        min_silence_samples = int(min_silence_sec * framerate) * n_channels
        split_points = [0]
        consecutive_silent = 0

        for idx, samp in enumerate(samples):
            if abs(samp) <= silence_threshold:
                consecutive_silent += 1
            else:
                if consecutive_silent >= min_silence_samples:
                    mid_point = idx - (consecutive_silent // 2)
                    aligned_mid = (mid_point // n_channels) * n_channels
                    split_points.append(aligned_mid)
                consecutive_silent = 0

        split_points.append(len(samples))

        output_dir.mkdir(parents=True, exist_ok=True)
        chapter_num = 1

        for i in range(len(split_points) - 1):
            start = split_points[i]
            end = split_points[i + 1]
            seg_samples = samples[start:end]

            if len(seg_samples) < framerate * n_channels:  # Ignore fragments < 1 sec
                continue

            seg_fmt = f"<{len(seg_samples)}h"
            packed_data = struct.pack(seg_fmt, *seg_samples)

            out_name = f"{prefix}{chapter_num:02d}.wav"
            out_file = output_dir / out_name

            # pylint: disable=no-member
            with wave.open(str(out_file), "wb") as w_wav:
                w_wav.setnchannels(n_channels)
                w_wav.setsampwidth(samp_width)
                w_wav.setframerate(framerate)
                w_wav.writeframes(packed_data)

            chapter_files.append(out_file)
            chapter_num += 1

        logger.info(
            "Natively split podcast %s into %d chapters.",
            input_wav.name,
            len(chapter_files),
        )
        return chapter_files
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Exception in native WAV podcast splitter: %s", exc)
        return chapter_files


def detect_silence_timestamps_ffmpeg(
    input_file: Path,
    min_silence_sec: float = 1.5,
    threshold_db: str = "-40dB",
) -> List[float]:
    """Detect silence timestamps using FFmpeg silencedetect filter.

    Args:
        input_file: Input audio file path.
        min_silence_sec: Minimum silence duration in seconds.
        threshold_db: Silence threshold decibels.

    Returns:
        List of mid-silence timestamp floats in seconds.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return []

    cmd = [
        ffmpeg_bin,
        "-i",
        str(input_file),
        "-af",
        f"silencedetect=noise={threshold_db}:d={min_silence_sec}",
        "-f",
        "null",
        "-",
    ]

    split_timestamps: List[float] = []
    try:
        res = subprocess.run(  # nosec B603
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )

        silence_starts: List[float] = []
        silence_ends: List[float] = []

        for line in res.stderr.splitlines():
            if "silence_start:" in line:
                m = re.search(r"silence_start:\s*([\d\.]+)", line)
                if m:
                    silence_starts.append(float(m.group(1)))
            elif "silence_end:" in line:
                m = re.search(r"silence_end:\s*([\d\.]+)", line)
                if m:
                    silence_ends.append(float(m.group(1)))

        for start, end in zip(silence_starts, silence_ends):
            split_timestamps.append((start + end) / 2.0)

        return split_timestamps
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Exception running FFmpeg silencedetect: %s", exc)
        return []


def split_audio_podcast(
    input_file: Path,
    output_dir: Path,
    min_silence_sec: float = 1.5,
    prefix: str = "chapter_",
) -> List[Path]:
    """Split audio podcast file into chapters.

    Args:
        input_file: Input audio file path.
        output_dir: Target output directory for chapter files.
        min_silence_sec: Minimum silence duration threshold.
        prefix: Chapter output filename prefix.

    Returns:
        List of output chapter file paths.
    """
    if input_file.suffix.lower() == ".wav":
        chapters = split_wav_silence_native(
            input_file,
            output_dir,
            min_silence_sec=min_silence_sec,
            prefix=prefix,
        )
        if chapters:
            return chapters

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        logger.error("Cannot split audio: FFmpeg is missing.")
        return []

    timestamps = detect_silence_timestamps_ffmpeg(input_file, min_silence_sec)
    if not timestamps:
        logger.warning("No silence split boundaries detected in: %s", input_file)
        return []

    # Segment audio file using detected timestamps
    output_dir.mkdir(parents=True, exist_ok=True)
    times_str = ",".join(f"{t:.3f}" for t in timestamps)
    ext = input_file.suffix.lower()
    out_pattern = str(output_dir / f"{prefix}%02d{ext}")

    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        str(input_file),
        "-f",
        "segment",
        "-segment_times",
        times_str,
        "-c",
        "copy",
        out_pattern,
    ]

    try:
        res = subprocess.run(  # nosec B603
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )
        if res.returncode == 0:
            created = sorted(list(output_dir.glob(f"{prefix}*{ext}")))
            logger.info("Split audio into %d chapter files via FFmpeg.", len(created))
            return created

        logger.error("FFmpeg segment error: %s", res.stderr)
        return []
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Exception in FFmpeg audio segment: %s", exc)
        return []


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Split long audio files or podcasts into chapters using silence detection."
        )
    )
    parser.add_argument(
        "input",
        type=str,
        help="Input audio file path.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Output directory path for chapters. Defaults to input directory.",
    )
    parser.add_argument(
        "-s",
        "--silence",
        type=float,
        default=1.5,
        help="Minimum silence duration in seconds to trigger split (default: 1.5).",
    )
    parser.add_argument(
        "-p",
        "--prefix",
        default="chapter_",
        help="Filename prefix for generated chapter files (default: 'chapter_').",
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

    input_file = Path(parsed_args.input)
    if not input_file.exists() or not input_file.is_file():
        logger.error("Input audio file does not exist: %s", input_file)
        return 1

    if input_file.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
        logger.error("Unsupported audio format: %s", input_file.suffix)
        return 1

    if parsed_args.output:
        out_dir = Path(parsed_args.output)
    else:
        out_dir = input_file.parent / f"{input_file.stem}_chapters"
    chapters = split_audio_podcast(
        input_file,
        out_dir,
        min_silence_sec=parsed_args.silence,
        prefix=parsed_args.prefix,
    )
    return 0 if chapters else 1


if __name__ == "__main__":
    sys.exit(main())
