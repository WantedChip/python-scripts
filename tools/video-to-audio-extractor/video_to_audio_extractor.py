"""Extract audio tracks from video files as MP3, WAV, or AAC audio formats.

This module uses ffmpeg CLI subprocess bindings to extract high-quality audio
streams from input video containers into standalone audio files.
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

SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm"}


def extract_audio(
    video_path: Path,
    output_path: Path,
    audio_format: str = "mp3",
    bitrate: str = "192k",
    overwrite: bool = True,
) -> bool:
    """Extract audio stream from video using ffmpeg CLI.

    Args:
        video_path: Input video file path.
        output_path: Target output audio file path.
        audio_format: Desired audio format ('mp3', 'wav', 'aac').
        bitrate: Audio bitrate (e.g. '192k', '256k', '320k').
        overwrite: If True, overwrites existing destination audio file.

    Returns:
        True if extraction succeeds, False if ffmpeg is missing or extraction fails.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        logger.error("FFmpeg executable was not found on system PATH.")
        return False

    if not video_path.exists() or not video_path.is_file():
        logger.error("Input video file does not exist: %s", video_path)
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg_bin,
        "-y" if overwrite else "-n",
        "-i",
        str(video_path),
        "-vn",
    ]

    if audio_format.lower() == "mp3":
        cmd.extend(["-acodec", "libmp3lame", "-ab", bitrate])
    elif audio_format.lower() == "wav":
        cmd.extend(["-acodec", "pcm_s16le"])
    elif audio_format.lower() == "aac":
        cmd.extend(["-acodec", "aac", "-ab", bitrate])

    cmd.append(str(output_path))

    try:
        res = subprocess.run(  # nosec B603
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )
        if res.returncode == 0 and output_path.exists():
            logger.info("Extracted audio: %s -> %s", video_path.name, output_path.name)
            return True

        logger.error("FFmpeg error extracting audio: %s", res.stderr)
        return False
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Exception running FFmpeg extraction: %s", exc)
        return False


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description="Extract audio tracks from video files as MP3, WAV, or AAC."
    )
    parser.add_argument(
        "input",
        type=str,
        help="Input video file or directory path.",
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
        choices=["mp3", "wav", "aac"],
        default="mp3",
        help="Target audio output format (default: mp3).",
    )
    parser.add_argument(
        "-b",
        "--bitrate",
        default="192k",
        help="Target audio bitrate (default: '192k').",
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
            "FFmpeg is required for audio extraction. "
            "Please install FFmpeg and ensure it is on your PATH."
        )
        return 1

    input_path = Path(parsed_args.input)
    if not input_path.exists():
        logger.error("Input path does not exist: %s", input_path)
        return 1

    video_files: List[Path] = []
    if input_path.is_file():
        video_files.append(input_path)
    elif input_path.is_dir():
        for root, _, filenames in os.walk(input_path):
            for fname in filenames:
                p = Path(root) / fname
                if p.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS:
                    video_files.append(p)

    if not video_files:
        logger.warning("No supported video files found to process.")
        return 0

    out_dir = Path(parsed_args.output) if parsed_args.output else input_path.parent
    if input_path.is_dir() and not parsed_args.output:
        out_dir = input_path

    fmt = parsed_args.format.lower()
    success_cnt = 0

    for src in video_files:
        rel = src.relative_to(input_path) if input_path.is_dir() else Path(src.name)
        dst = out_dir / rel.parent / f"{rel.stem}.{fmt}"

        ok = extract_audio(
            src,
            dst,
            audio_format=fmt,
            bitrate=parsed_args.bitrate,
        )
        if ok:
            success_cnt += 1

    logger.info(
        "Successfully extracted audio from %d/%d video files.",
        success_cnt,
        len(video_files),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
