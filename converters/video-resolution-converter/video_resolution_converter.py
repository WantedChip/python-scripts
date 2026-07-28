"""Convert videos to standard resolutions (480p, 720p, 1080p, 4K) in batch.

This module converts video files to standard target height resolutions while preserving
original aspect ratios using FFmpeg scaling filters via subprocess bindings.
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
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm"}

RESOLUTION_PRESETS: Dict[str, Tuple[int, int]] = {
    "360p": (-2, 360),
    "480p": (-2, 480),
    "720p": (-2, 720),
    "1080p": (-2, 1080),
    "1440p": (-2, 1440),
    "4k": (-2, 2160),
}


def convert_video_resolution(
    video_path: Path,
    output_path: Path,
    resolution: str = "720p",
    crf: int = 23,
    preset: str = "medium",
    overwrite: bool = True,
) -> bool:
    """Convert video resolution using FFmpeg scale filter.

    Args:
        video_path: Input video file path.
        output_path: Target converted video file path.
        resolution: Preset resolution name ('480p', '720p', '1080p', '4k') or 'W:H'.
        crf: Constant Rate Factor compression quality (0-51, default: 23).
        preset: FFmpeg x264 encoding preset speed (e.g. 'fast', 'medium', 'slow').
        overwrite: Overwrite destination file if True.

    Returns:
        True if video resolution conversion succeeded, False otherwise.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        logger.error("FFmpeg executable was not found on system PATH.")
        return False

    if not video_path.exists() or not video_path.is_file():
        logger.error("Input video file does not exist: %s", video_path)
        return False

    res_lower = resolution.lower()
    if res_lower in RESOLUTION_PRESETS:
        w, h = RESOLUTION_PRESETS[res_lower]
        scale_filter = f"scale={w}:{h}"
    elif ":" in resolution:
        scale_filter = f"scale={resolution}"
    else:
        logger.error("Unsupported resolution preset or format: %s", resolution)
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg_bin,
        "-y" if overwrite else "-n",
        "-i",
        str(video_path),
        "-vf",
        scale_filter,
        "-c:v",
        "libx264",
        "-crf",
        str(crf),
        "-preset",
        preset,
        "-c:a",
        "aac",
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
                "Converted resolution (%s): %s -> %s",
                resolution,
                video_path.name,
                output_path.name,
            )
            return True

        logger.error("FFmpeg resolution conversion error: %s", res.stderr)
        return False
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Exception running FFmpeg scale conversion: %s", exc)
        return False


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description="Convert videos to standard resolutions (480p, 720p, 1080p, 4k)."
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
        "-r",
        "--resolution",
        default="720p",
        help="Target resolution ('360p', '480p', '720p', '1080p', '4k') or W:H.",
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=23,
        help="x264 Constant Rate Factor quality 0-51 (default: 23).",
    )
    parser.add_argument(
        "--suffix",
        type=str,
        default="",
        help="Optional filename suffix for converted files (e.g. '_720p').",
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
            "FFmpeg is required for resolution conversion. "
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

    suf = parsed_args.suffix or f"_{parsed_args.resolution}"
    success_cnt = 0

    for src in video_files:
        rel = (
            src.relative_to(input_path)
            if input_path.is_dir()
            else Path(src.name)
        )
        dst = out_dir / rel.parent / f"{rel.stem}{suf}{rel.suffix}"

        ok = convert_video_resolution(
            src,
            dst,
            resolution=parsed_args.resolution,
            crf=parsed_args.crf,
        )
        if ok:
            success_cnt += 1

    logger.info(
        "Successfully converted resolution for %d/%d video files.",
        success_cnt,
        len(video_files),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
