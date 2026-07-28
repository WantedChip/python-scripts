"""Adjust playback speed of video files while preserving audio pitch using FFmpeg.

This module changes video playback speed (e.g. 0.5x slow-motion, 1.5x, 2.0x)
using FFmpeg setpts video filter and pitch-preserved atempo audio filter chain.
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


def build_atempo_filter(speed: float) -> str:
    """Build FFmpeg atempo audio filter chain for arbitrary speed factors.

    Args:
        speed: Speed multiplier float (e.g. 0.25, 0.5, 1.5, 4.0).

    Returns:
        Comma-separated atempo filter string.
    """
    filters: List[str] = []
    rem_speed = speed

    # FFmpeg atempo supports values between 0.5 and 2.0 per filter instance
    while rem_speed > 2.0:
        filters.append("atempo=2.0")
        rem_speed /= 2.0
    while rem_speed < 0.5:
        filters.append("atempo=0.5")
        rem_speed /= 0.5

    filters.append(f"atempo={rem_speed:.4f}")
    return ",".join(filters)


def change_video_speed(
    video_path: Path,
    output_path: Path,
    speed: float = 1.5,
    overwrite: bool = True,
) -> bool:
    """Change playback speed of video file while maintaining pitch for audio.

    Args:
        video_path: Input video file path.
        output_path: Target video file path.
        speed: Playback speed multiplier (e.g. 0.5 for slow motion, 2.0 for fast).
        overwrite: Overwrite destination file if True.

    Returns:
        True if video speed change succeeded, False otherwise.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        logger.error("FFmpeg executable was not found on system PATH.")
        return False

    if not video_path.exists() or not video_path.is_file():
        logger.error("Input video file does not exist: %s", video_path)
        return False

    if speed <= 0:
        logger.error("Invalid speed factor: %s. Speed must be > 0.", speed)
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)

    setpts_val = 1.0 / speed
    video_filter = f"setpts={setpts_val:.4f}*PTS"
    audio_filter = build_atempo_filter(speed)

    cmd = [
        ffmpeg_bin,
        "-y" if overwrite else "-n",
        "-i",
        str(video_path),
        "-filter:v",
        video_filter,
        "-filter:a",
        audio_filter,
        str(output_path),
    ]

    try:
        res = subprocess.run(  # nosec B603
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )
        if res.returncode == 0 and output_path.exists():
            logger.info(
                "Changed video speed (%.2fx): %s -> %s",
                speed,
                video_path.name,
                output_path.name,
            )
            return True

        logger.error("FFmpeg speed adjustment error: %s", res.stderr)
        return False
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Exception running FFmpeg speed adjustment: %s", exc)
        return False


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description="Adjust playback speed of video files while preserving audio pitch."
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
        help="Output directory or file path. Defaults to input location.",
    )
    parser.add_argument(
        "-s",
        "--speed",
        type=float,
        default=1.5,
        help="Speed multiplier float e.g. 0.5 (slow) or 2.0 (fast). Default: 1.5.",
    )
    parser.add_argument(
        "--suffix",
        type=str,
        default="",
        help="Optional filename suffix for modified output files (e.g. '_1.5x').",
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
            "FFmpeg is required for video speed adjustment. "
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

    suf = parsed_args.suffix or f"_{parsed_args.speed}x"
    success_cnt = 0

    for src in video_files:
        if (
            input_path.is_file()
            and parsed_args.output
            and Path(parsed_args.output).suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS
        ):
            dst = Path(parsed_args.output)
        else:
            rel = src.relative_to(input_path) if input_path.is_dir() else Path(src.name)
            dst = out_dir / rel.parent / f"{rel.stem}{suf}{rel.suffix}"

        ok = change_video_speed(
            src,
            dst,
            speed=parsed_args.speed,
        )
        if ok:
            success_cnt += 1

    logger.info(
        "Successfully adjusted speed for %d/%d video files.",
        success_cnt,
        len(video_files),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
