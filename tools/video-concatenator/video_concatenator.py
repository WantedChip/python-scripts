"""Joins multiple video clips into a single video file specified by order.

This module parses an ordered file list (JSON or TXT config) or CLI arguments
and uses FFmpeg concat demuxing or re-encoding to concatenate video clips into one.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import json
import logging
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

SUPPORTED_VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".webm",
}  # vulture: ignore


def load_clip_list_from_config(config_path: Path) -> List[Path]:
    """Parse ordered video clip file paths from a JSON or TXT config file.

    Args:
        config_path: Path to config file (JSON array or TXT lines).

    Returns:
        List of resolved Path objects for input video clips.
    """
    clips: List[Path] = []
    base_dir = config_path.parent

    if config_path.suffix.lower() == ".json":
        with open(config_path, "r", encoding="utf-8") as f_in:
            data = json.load(f_in)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        p = Path(item)
                        clips.append(p if p.is_absolute() else base_dir / p)
            elif isinstance(data, dict) and "files" in data:
                for item in data["files"]:
                    p = Path(item)
                    clips.append(p if p.is_absolute() else base_dir / p)
    else:  # TXT line per file format
        with open(config_path, "r", encoding="utf-8") as f_in:
            for line in f_in:
                clean = line.strip()
                if clean and not clean.startswith("#"):
                    p = Path(clean)
                    clips.append(p if p.is_absolute() else base_dir / p)

    return clips


def concatenate_videos_ffmpeg(
    clip_paths: List[Path], output_path: Path, reencode: bool = False
) -> bool:
    """Concatenate video clips using FFmpeg subprocess execution.

    Args:
        clip_paths: Ordered list of input video file paths.
        output_path: Target output video file path.
        reencode: Whether to force re-encoding audio/video streams.

    Returns:
        True if concatenation succeeded, False otherwise.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        logger.error(
            "FFmpeg executable not found on PATH. "
            "Please install FFmpeg to join videos."
        )
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as tmp_list:
        list_file_path = Path(tmp_list.name)
        for clip in clip_paths:
            escaped_path = str(clip.resolve()).replace("'", "'\\''")
            tmp_list.write(f"file '{escaped_path}'\n")

    try:
        if reencode:
            # Complex filter re-encode for clips with differing codecs/resolutions
            cmd = [ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i"]
            cmd.extend(
                [
                    str(list_file_path),
                    "-c:v",
                    "libx264",
                    "-c:a",
                    "aac",
                    str(output_path),
                ]
            )
        else:
            # Fast stream-copy concat demuxer
            cmd = [
                ffmpeg_bin,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file_path),
                "-c",
                "copy",
                str(output_path),
            ]

        res = subprocess.run(  # nosec B603
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        if res.returncode == 0 and output_path.exists():
            return True

        logger.error("FFmpeg failed with exit code %d: %s", res.returncode, res.stderr)
        return False
    finally:
        if list_file_path.exists():
            list_file_path.unlink()


def main(args: Optional[List[str]] = None) -> int:
    """Run CLI entry point for video concatenator tool.

    Args:
        args: Command line argument list.

    Returns:
        Exit code integer (0 for success, non-zero for failure).
    """
    parser = argparse.ArgumentParser(
        description="Join multiple video clips into one with ordered config."
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default=None,
        help="Path to JSON or TXT config file listing video clips in order.",
    )
    parser.add_argument(
        "-f",
        "--files",
        nargs="+",
        default=None,
        help="List of video file paths to join in order.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="concatenated_output.mp4",
        help="Output video file path (default: concatenated_output.mp4).",
    )
    parser.add_argument(
        "--reencode",
        action="store_true",
        help="Force re-encoding streams if codecs/resolutions differ.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging."
    )

    parsed_args = parser.parse_args(args)

    level = logging.DEBUG if parsed_args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    clip_paths: List[Path] = []

    if parsed_args.config:
        cfg_path = Path(parsed_args.config)
        if not cfg_path.exists():
            logger.error("Specified config file does not exist: %s", cfg_path)
            return 1
        clip_paths = load_clip_list_from_config(cfg_path)
    elif parsed_args.files:
        clip_paths = [Path(p) for p in parsed_args.files]
    else:
        logger.error(
            "Please specify either --config <file> or --files <file1> <file2> ..."
        )
        return 1

    missing_files = [p for p in clip_paths if not p.exists()]
    if missing_files:
        logger.error("The following video files were not found: %s", missing_files)
        return 1

    if not clip_paths:
        logger.error("No valid video clips found to concatenate.")
        return 1

    logger.info(
        "Concatenating %d video clips into %s...",
        len(clip_paths),
        parsed_args.output,
    )
    out_path = Path(parsed_args.output)
    success = concatenate_videos_ffmpeg(clip_paths, out_path, parsed_args.reencode)

    if success:
        logger.info("Successfully concatenated video saved to %s", out_path.resolve())
        return 0

    logger.error("Failed to concatenate video clips.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
