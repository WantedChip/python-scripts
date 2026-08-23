"""Scans a folder of videos and reports their durations in a CSV summary or table.

This tool extracts video metadata (duration, resolution, codecs, file size)
using FFmpeg/ffprobe subprocess calls or native binary header parsing fallbacks.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import csv
import json
import logging
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

SUPPORTED_VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".webm",
    ".m4v",
}  # vulture: ignore


def format_duration(seconds: float) -> str:
    """Format duration in seconds into HH:MM:SS format string.

    Args:
        seconds: Duration in seconds float.

    Returns:
        Formatted string as HH:MM:SS.
    """
    total_sec = max(0, int(seconds))
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    secs = total_sec % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def get_video_metadata_ffprobe(video_path: Path) -> Optional[Dict[str, Any]]:
    """Probe video file metadata using ffprobe executable.

    Args:
        video_path: Path to target video file.

    Returns:
        Dictionary of video metadata if ffprobe succeeds, else None.
    """
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        return None

    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]

    try:
        # Bandit flags subprocess with a list as B603; inputs are local file
        # paths and the ffprobe binary resolved via shutil.which, no shell.
        res = subprocess.run(  # nosec B603
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if res.returncode != 0 or not res.stdout.strip():
            return None

        data = json.loads(res.stdout)
        format_info = data.get("format", {})
        streams = data.get("streams", [])

        duration = float(format_info.get("duration", 0.0))
        size_bytes = int(format_info.get("size", video_path.stat().st_size))

        video_stream: Dict[str, Any] = next(
            (s for s in streams if s.get("codec_type") == "video"), {}
        )
        audio_stream: Dict[str, Any] = next(
            (s for s in streams if s.get("codec_type") == "audio"), {}
        )

        width = video_stream.get("width", 0)
        height = video_stream.get("height", 0)
        v_codec = video_stream.get("codec_name", "unknown")
        a_codec = audio_stream.get("codec_name", "none")

        return {
            "path": str(video_path),
            "filename": video_path.name,
            "duration_seconds": round(duration, 2),
            "duration_formatted": format_duration(duration),
            "width": width,
            "height": height,
            "resolution": f"{width}x{height}" if width and height else "unknown",
            "v_codec": v_codec,
            "a_codec": a_codec,
            "size_bytes": size_bytes,
        }
    except (json.JSONDecodeError, ValueError, OSError) as err:
        logger.debug("ffprobe failed for %s: %s", video_path, err)
        return None


def get_video_metadata_native(video_path: Path) -> Dict[str, Any]:
    """Fallback parser for video metadata using native binary inspection.

    Args:
        video_path: Path to target video file.

    Returns:
        Dictionary of video metadata estimates.
    """
    size_bytes = video_path.stat().st_size
    duration_seconds = 0.0

    if video_path.suffix.lower() in (".mp4", ".m4v", ".mov"):
        duration_seconds = parse_mp4_duration(video_path)

    return {
        "path": str(video_path),
        "filename": video_path.name,
        "duration_seconds": round(duration_seconds, 2),
        "duration_formatted": format_duration(duration_seconds),
        "width": 0,
        "height": 0,
        "resolution": "unknown",
        "v_codec": "unknown",
        "a_codec": "unknown",
        "size_bytes": size_bytes,
    }


def parse_mp4_duration(video_path: Path) -> float:
    """Extract duration from MP4 mvhd atom header.

    Args:
        video_path: Path to MP4 file.

    Returns:
        Extracted duration in seconds float, or 0.0 if parsing fails.
    """
    try:
        with open(video_path, "rb") as f_in:
            content = f_in.read(1024 * 1024)
            mvhd_idx = content.find(b"mvhd")
            if mvhd_idx != -1 and mvhd_idx + 8 <= len(content):
                version = content[mvhd_idx + 4]
                if version == 0 and mvhd_idx + 24 <= len(content):
                    timescale = int.from_bytes(
                        content[mvhd_idx + 16 : mvhd_idx + 20],  # noqa: E203
                        "big",
                    )
                    duration = int.from_bytes(
                        content[mvhd_idx + 20 : mvhd_idx + 24],  # noqa: E203
                        "big",
                    )
                    if timescale > 0:
                        return duration / float(timescale)
                elif version == 1 and mvhd_idx + 36 <= len(content):
                    timescale = int.from_bytes(
                        content[mvhd_idx + 24 : mvhd_idx + 28],  # noqa: E203
                        "big",
                    )
                    duration = int.from_bytes(
                        content[mvhd_idx + 28 : mvhd_idx + 36],  # noqa: E203
                        "big",
                    )
                    if timescale > 0:
                        return duration / float(timescale)
    except OSError as err:
        logger.debug("MP4 header parse error: %s", err)
    return 0.0


def scan_video_directory(
    target_dir: Path, recursive: bool = False
) -> Tuple[List[Dict[str, Any]], float]:
    """Scan directory for video files and extract their duration metrics.

    Args:
        target_dir: Directory containing video files.
        recursive: Whether to scan subdirectories recursively.

    Returns:
        Tuple containing list of metadata dicts and total accumulated duration.
    """
    pattern = "**/*" if recursive else "*"
    video_files: List[Path] = []

    for item in target_dir.glob(pattern):
        if item.is_file() and item.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS:
            video_files.append(item)

    video_files.sort(key=lambda p: str(p).lower())

    results: List[Dict[str, Any]] = []
    total_seconds = 0.0

    for v_path in video_files:
        meta = get_video_metadata_ffprobe(v_path)
        if meta is None:
            meta = get_video_metadata_native(v_path)
        results.append(meta)
        total_seconds += meta["duration_seconds"]

    return results, total_seconds


def export_csv_report(results: List[Dict[str, Any]], output_path: Path) -> None:
    """Export video duration results to CSV summary file.

    Args:
        results: List of video metadata dictionaries.
        output_path: Target CSV file path.
    """
    fieldnames = [
        "filename",
        "duration_formatted",
        "duration_seconds",
        "resolution",
        "width",
        "height",
        "v_codec",
        "a_codec",
        "size_bytes",
        "path",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)


def main(args: Optional[List[str]] = None) -> int:
    """Run CLI entry point for video duration reporter.

    Args:
        args: Command line argument list.

    Returns:
        Exit code integer (0 for success, non-zero for failure).
    """
    parser = argparse.ArgumentParser(
        description="Scan folder of videos and report durations in CSV summary."
    )
    parser.add_argument("directory", type=str, help="Directory containing video files.")
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Scan directory recursively.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Target CSV summary output path.",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["csv", "json", "table"],
        default="table",
        help="Console output format (default: table).",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging."
    )

    parsed_args = parser.parse_args(args)

    level = logging.DEBUG if parsed_args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    target_dir = Path(parsed_args.directory)
    if not target_dir.exists() or not target_dir.is_dir():
        logger.error("Specified directory does not exist: %s", target_dir)
        return 1

    results, total_seconds = scan_video_directory(target_dir, parsed_args.recursive)

    if parsed_args.output:
        out_path = Path(parsed_args.output)
        export_csv_report(results, out_path)
        logger.info("CSV summary exported to: %s", out_path)

    if parsed_args.format == "json":
        output_data = {
            "total_videos": len(results),
            "total_duration_seconds": round(total_seconds, 2),
            "total_duration_formatted": format_duration(total_seconds),
            "videos": results,
        }
        print(json.dumps(output_data, indent=2))
    elif parsed_args.format == "csv":
        fieldnames = [
            "filename",
            "duration_formatted",
            "duration_seconds",
            "resolution",
            "size_bytes",
        ]
        writer = csv.DictWriter(
            sys.stdout, fieldnames=fieldnames, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(results)
    else:  # table
        print(f"\nVideo Duration Summary ({len(results)} videos found)")
        print("-" * 65)
        hdr = (
            f"{'Filename':<30} | {'Duration':<10} | "
            f"{'Resolution':<12} | {'Size (MB)':<8}"
        )
        print(hdr)
        print("-" * 65)
        for item in results:
            fname = (
                item["filename"][:27] + "..."
                if len(item["filename"]) > 30
                else item["filename"]
            )
            mb_size = round(item["size_bytes"] / (1024 * 1024), 2)
            print(
                f"{fname:<30} | {item['duration_formatted']:<10} | "
                f"{item['resolution']:<12} | {mb_size:<8}"
            )
        print("-" * 65)
        print(
            f"Total Duration: {format_duration(total_seconds)} "
            f"({round(total_seconds, 2)}s)\n"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
