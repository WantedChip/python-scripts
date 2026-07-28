"""Overlay an image logo or text watermark on video files at specified positions.

This module overlays watermark images or text captions onto video files using
FFmpeg overlay / drawtext video filters.
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

POSITION_PRESETS = {
    "top-left": ("10", "10"),
    "top-right": ("main_w-overlay_w-10", "10"),
    "bottom-left": ("10", "main_h-overlay_h-10"),
    "bottom-right": ("main_w-overlay_w-10", "main_h-overlay_h-10"),
    "center": ("(main_w-overlay_w)/2", "(main_h-overlay_h)/2"),
}

TEXT_POSITION_PRESETS = {
    "top-left": ("10", "10"),
    "top-right": ("w-text_w-10", "10"),
    "bottom-left": ("10", "h-text_h-10"),
    "bottom-right": ("w-text_w-10", "h-text_h-10"),
    "center": ("(w-text_w)/2", "(h-text_h)/2"),
}


def add_image_watermark(
    video_path: Path,
    watermark_path: Path,
    output_path: Path,
    position: str = "bottom-right",
    overwrite: bool = True,
) -> bool:
    """Overlay an image watermark on a video file using FFmpeg overlay filter.

    Args:
        video_path: Input video file path.
        watermark_path: Input watermark image file path (PNG, JPG).
        output_path: Target watermarked output video path.
        position: Position preset ('top-left', 'bottom-right', 'center', etc.).
        overwrite: Overwrite destination file if True.

    Returns:
        True if image watermarking succeeded, False otherwise.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        logger.error("FFmpeg executable was not found on system PATH.")
        return False

    if not video_path.exists() or not watermark_path.exists():
        logger.error("Video or watermark image file missing.")
        return False

    pos_x, pos_y = POSITION_PRESETS.get(position, POSITION_PRESETS["bottom-right"])
    filter_spec = f"[1:v]format=rgba[wm];[0:v][wm]overlay={pos_x}:{pos_y}"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg_bin,
        "-y" if overwrite else "-n",
        "-i",
        str(video_path),
        "-i",
        str(watermark_path),
        "-filter_complex",
        filter_spec,
        "-c:a",
        "copy",
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
                "Added image watermark: %s -> %s",
                video_path.name,
                output_path.name,
            )
            return True

        logger.error("FFmpeg image watermark error: %s", res.stderr)
        return False
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Exception running FFmpeg image watermark: %s", exc)
        return False


def add_text_watermark(
    video_path: Path,
    text: str,
    output_path: Path,
    position: str = "bottom-right",
    font_size: int = 24,
    font_color: str = "white",
    overwrite: bool = True,
) -> bool:
    """Overlay a text watermark on a video file using FFmpeg drawtext filter.

    Args:
        video_path: Input video file path.
        text: Watermark text string.
        output_path: Target watermarked output video path.
        position: Position preset ('top-left', 'bottom-right', 'center', etc.).
        font_size: Text font size in points (default: 24).
        font_color: Text font color string (default: 'white').
        overwrite: Overwrite destination file if True.

    Returns:
        True if text watermarking succeeded, False otherwise.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        logger.error("FFmpeg executable was not found on system PATH.")
        return False

    if not video_path.exists():
        logger.error("Input video file missing: %s", video_path)
        return False

    pos_x, pos_y = TEXT_POSITION_PRESETS.get(
        position, TEXT_POSITION_PRESETS["bottom-right"]
    )
    escaped_text = text.replace(":", "\\:").replace("'", "\\'")
    filter_spec = (
        f"drawtext=text='{escaped_text}':x={pos_x}:y={pos_y}:"
        f"fontsize={font_size}:fontcolor={font_color}"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg_bin,
        "-y" if overwrite else "-n",
        "-i",
        str(video_path),
        "-vf",
        filter_spec,
        "-c:a",
        "copy",
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
                "Added text watermark: %s -> %s",
                video_path.name,
                output_path.name,
            )
            return True

        logger.error("FFmpeg text watermark error: %s", res.stderr)
        return False
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Exception running FFmpeg text watermark: %s", exc)
        return False


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description="Overlay an image logo or text watermark on video files."
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
        "-w",
        "--watermark",
        type=str,
        help="Path to watermark image logo file.",
    )
    parser.add_argument(
        "-t",
        "--text",
        type=str,
        help="Watermark text string (used if image watermark is not provided).",
    )
    parser.add_argument(
        "-p",
        "--position",
        choices=["top-left", "top-right", "bottom-left", "bottom-right", "center"],
        default="bottom-right",
        help="Watermark position preset (default: 'bottom-right').",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=24,
        help="Text font size in points (default: 24).",
    )
    parser.add_argument(
        "--suffix",
        type=str,
        default="_wm",
        help="Filename suffix for watermarked files (default: '_wm').",
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
            "FFmpeg is required for video watermarking. "
            "Please install FFmpeg and ensure it is on your PATH."
        )
        return 1

    if not parsed_args.watermark and not parsed_args.text:
        logger.error("Must specify either --watermark image path or --text string.")
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

        if parsed_args.watermark:
            ok = add_image_watermark(
                src,
                Path(parsed_args.watermark),
                dst,
                position=parsed_args.position,
            )
        else:
            ok = add_text_watermark(
                src,
                parsed_args.text,
                dst,
                position=parsed_args.position,
                font_size=parsed_args.size,
            )
        if ok:
            success_cnt += 1

    logger.info(
        "Successfully watermarked %d/%d video files.",
        success_cnt,
        len(video_files),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
