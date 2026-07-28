"""Extract frame images at specified timestamps from video files to use as thumbnails.

This module extracts single-frame high-resolution images (PNG, JPEG, WebP) from video
containers using FFmpeg subprocess execution.
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


def extract_video_thumbnail(
    video_path: Path,
    output_image_path: Path,
    timestamp: str = "00:00:01",
    scale_width: Optional[int] = None,
    overwrite: bool = True,
) -> bool:
    """Extract a thumbnail frame image from a video at a specified timestamp.

    Args:
        video_path: Input video file path.
        output_image_path: Target output image file path (PNG, JPG, WebP).
        timestamp: Time position 'HH:MM:SS' or seconds string (default: '00:00:01').
        scale_width: Optional target width in pixels (height scales automatically).
        overwrite: Overwrite destination image file if True.

    Returns:
        True if frame extraction succeeded, False otherwise.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        logger.error("FFmpeg executable was not found on system PATH.")
        return False

    if not video_path.exists() or not video_path.is_file():
        logger.error("Input video file does not exist: %s", video_path)
        return False

    output_image_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg_bin,
        "-y" if overwrite else "-n",
        "-ss",
        timestamp,
        "-i",
        str(video_path),
        "-vframes",
        "1",
    ]

    if scale_width and scale_width > 0:
        cmd.extend(["-vf", f"scale={scale_width}:-1"])

    cmd.append(str(output_image_path))

    try:
        res = subprocess.run(  # nosec B603
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )
        if res.returncode == 0 and output_image_path.exists():
            logger.info(
                "Extracted thumbnail frame (%s): %s -> %s",
                timestamp,
                video_path.name,
                output_image_path.name,
            )
            return True

        logger.error("FFmpeg thumbnail extraction error: %s", res.stderr)
        return False
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Exception running FFmpeg thumbnail extraction: %s", exc)
        return False


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description="Extract frame images at specified timestamps as video thumbnails."
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
        "-ss",
        "--time",
        default="00:00:01",
        help="Timestamp position HH:MM:SS or seconds (default: '00:00:01').",
    )
    parser.add_argument(
        "-w",
        "--width",
        type=int,
        help="Optional thumbnail width in pixels (height scales proportionally).",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["jpg", "png", "webp"],
        default="jpg",
        help="Thumbnail image format (default: 'jpg').",
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
            "FFmpeg is required for thumbnail extraction. "
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
        if (
            input_path.is_file()
            and parsed_args.output
            and Path(parsed_args.output).suffix.lower()
            in {".jpg", ".jpeg", ".png", ".webp"}
        ):
            dst = Path(parsed_args.output)
        else:
            rel = src.relative_to(input_path) if input_path.is_dir() else Path(src.name)
            dst = out_dir / rel.parent / f"{rel.stem}_thumb.{fmt}"

        ok = extract_video_thumbnail(
            src,
            dst,
            timestamp=parsed_args.time,
            scale_width=parsed_args.width,
        )
        if ok:
            success_cnt += 1

    logger.info(
        "Successfully extracted thumbnails for %d/%d video files.",
        success_cnt,
        len(video_files),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
