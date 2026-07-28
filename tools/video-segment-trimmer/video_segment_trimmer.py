"""Trim video files to a specified start and end timestamp using FFmpeg.

This module trims specified time segments from video files using fast stream copying
or frame-accurate re-encoding via FFmpeg CLI bindings.
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


def trim_video_segment(
    video_path: Path,
    output_path: Path,
    start_time: str = "00:00:00",
    end_time: Optional[str] = None,
    duration: Optional[str] = None,
    copy_codec: bool = True,
    overwrite: bool = True,
) -> bool:
    """Trim a segment from a video file using FFmpeg.

    Args:
        video_path: Input video file path.
        output_path: Target trimmed output video file path.
        start_time: Start timestamp ('HH:MM:SS' or seconds string).
        end_time: Optional end timestamp ('HH:MM:SS' or seconds string).
        duration: Optional segment duration string.
        copy_codec: Fast lossless stream copy without re-encoding if True.
        overwrite: Overwrite destination file if True.

    Returns:
        True if video segment was trimmed successfully, False otherwise.
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
        "-ss",
        start_time,
        "-i",
        str(video_path),
    ]

    if end_time:
        cmd.extend(["-to", end_time])
    elif duration:
        cmd.extend(["-t", duration])

    if copy_codec:
        cmd.extend(["-c", "copy"])

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
            logger.info(
                "Trimmed video segment: %s -> %s",
                video_path.name,
                output_path.name,
            )
            return True

        logger.error("FFmpeg error trimming video: %s", res.stderr)
        return False
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Exception running FFmpeg trim: %s", exc)
        return False


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description="Trim video files to a specified start and end timestamp."
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
        "--start",
        default="00:00:00",
        help="Start timestamp HH:MM:SS or seconds (default: '00:00:00').",
    )
    parser.add_argument(
        "-to",
        "--end",
        help="End timestamp HH:MM:SS or seconds.",
    )
    parser.add_argument(
        "-t",
        "--duration",
        help="Segment duration in seconds or HH:MM:SS.",
    )
    parser.add_argument(
        "--reencode",
        action="store_true",
        help="Re-encode stream for frame accuracy instead of fast stream copy.",
    )
    parser.add_argument(
        "--suffix",
        type=str,
        default="_trimmed",
        help="Filename suffix for trimmed output files (default: '_trimmed').",
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
            "FFmpeg is required for video trimming. "
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
            dst = out_dir / rel.parent / f"{rel.stem}{parsed_args.suffix}{rel.suffix}"

        ok = trim_video_segment(
            src,
            dst,
            start_time=parsed_args.start,
            end_time=parsed_args.end,
            duration=parsed_args.duration,
            copy_codec=not parsed_args.reencode,
        )
        if ok:
            success_cnt += 1

    logger.info(
        "Successfully trimmed %d/%d video files.",
        success_cnt,
        len(video_files),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
