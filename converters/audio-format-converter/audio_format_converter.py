"""Convert audio files between MP3, WAV, FLAC, OGG, and AAC formats in bulk.

This module converts audio containers and codecs using FFmpeg subprocess execution
with configurable bitrate, sample rate, and target output directory.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import logging
import os
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".aac", ".ogg", ".m4a"}


def convert_audio_format(
    input_file: Path,
    output_file: Path,
    target_format: str = "mp3",
    bitrate: str = "192k",
    sample_rate: Optional[int] = None,
    overwrite: bool = True,
) -> bool:
    """Convert single audio file to target format using FFmpeg.

    Args:
        input_file: Input audio file path.
        output_file: Target converted audio file path.
        target_format: Format string ('mp3', 'wav', 'flac', 'ogg', 'aac').
        bitrate: Audio bitrate (e.g. '192k', '320k').
        sample_rate: Optional target sampling frequency in Hz (e.g. 44100, 48000).
        overwrite: Overwrite destination file if True.

    Returns:
        True if audio conversion succeeded, False otherwise.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        logger.error("FFmpeg executable was not found on system PATH.")
        return False

    if not input_file.exists() or not input_file.is_file():
        logger.error("Input audio file does not exist: %s", input_file)
        return False

    output_file.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg_bin,
        "-y" if overwrite else "-n",
        "-i",
        str(input_file),
    ]

    fmt_lower = target_format.lower().lstrip(".")
    if fmt_lower == "mp3":
        cmd.extend(["-c:a", "libmp3lame", "-b:a", bitrate])
    elif fmt_lower == "wav":
        cmd.extend(["-c:a", "pcm_s16le"])
    elif fmt_lower == "flac":
        cmd.extend(["-c:a", "flac"])
    elif fmt_lower == "ogg":
        cmd.extend(["-c:a", "libvorbis", "-q:a", "5"])
    elif fmt_lower == "aac":
        cmd.extend(["-c:a", "aac", "-b:a", bitrate])

    if sample_rate and sample_rate > 0:
        cmd.extend(["-ar", str(sample_rate)])

    cmd.append(str(output_file))

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
                "Converted audio (%s): %s -> %s",
                fmt_lower,
                input_file.name,
                output_file.name,
            )
            return True

        logger.error("FFmpeg audio conversion error: %s", res.stderr)
        return False
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Exception running FFmpeg audio conversion: %s", exc)
        return False


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description="Convert audio files between MP3, WAV, FLAC, OGG, and AAC in bulk."
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
        "-f",
        "--format",
        choices=["mp3", "wav", "flac", "ogg", "aac"],
        default="mp3",
        help="Target audio format (default: 'mp3').",
    )
    parser.add_argument(
        "-b",
        "--bitrate",
        default="192k",
        help="Audio bitrate (default: '192k').",
    )
    parser.add_argument(
        "-ar",
        "--samplerate",
        type=int,
        help="Target sample rate in Hz (e.g. 44100, 48000).",
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

    if not shutil.which("ffmpeg"):
        logger.error(
            "FFmpeg is required for audio format conversion. "
            "Please install FFmpeg and ensure it is on your PATH."
        )
        return 1

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

    fmt = parsed_args.format.lower()
    success_cnt = 0

    for src in audio_files:
        rel = src.relative_to(input_path) if input_path.is_dir() else Path(src.name)
        dst = out_dir / rel.parent / f"{rel.stem}.{fmt}"

        ok = convert_audio_format(
            src,
            dst,
            target_format=fmt,
            bitrate=parsed_args.bitrate,
            sample_rate=parsed_args.samplerate,
        )
        if ok:
            success_cnt += 1

    logger.info(
        "Successfully converted %d/%d audio files to %s.",
        success_cnt,
        len(audio_files),
        fmt,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
