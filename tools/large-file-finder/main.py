"""Large File Finder.

Scans directory trees for files exceeding specified size thresholds,
providing sorted file reports, extension breakdowns, and multi-format exports.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

SIZE_UNITS = {
    "B": 1,
    "KB": 1024,
    "K": 1024,
    "MB": 1024**2,
    "M": 1024**2,
    "GB": 1024**3,
    "G": 1024**3,
    "TB": 1024**4,
    "T": 1024**4,
}


def parse_size_string(size_str: Union[str, int, float]) -> int:
    """Parse size strings like '100MB', '1.5GB', '500KB' into byte counts.

    Args:
        size_str: Size string.

    Returns:
        Integer number of bytes.

    Raises:
        ValueError: If size format is invalid.
    """
    if isinstance(size_str, (int, float)):
        return int(size_str)

    size_str = str(size_str).strip().upper()
    match = re.match(r"^([\d.]+)\s*([A-Z]*)$", size_str)
    if not match:
        raise ValueError(f"Invalid size specification: '{size_str}'")

    number, unit = match.groups()
    val = float(number)

    if not unit:
        return int(val)

    if unit in SIZE_UNITS:
        return int(val * SIZE_UNITS[unit])

    raise ValueError(f"Unknown size unit '{unit}' in '{size_str}'")


def format_bytes(bytes_count: Union[int, float]) -> str:
    """Format byte counts into human-readable string (e.g. 1.25 MB)."""
    count = float(bytes_count)
    if count < 1024:
        return f"{int(count)} B"
    for unit in ["KB", "MB", "GB", "TB"]:
        count /= 1024.0
        if count < 1024:
            return f"{count:.2f} {unit}"
    return f"{count:.2f} PB"


def scan_large_files(
    root_dir: Path, min_size_bytes: int, top_n: Optional[int] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """Scan directory recursively for files >= min_size_bytes.

    Args:
        root_dir: Root directory path.
        min_size_bytes: Minimum byte threshold.
        top_n: Optional limit on number of top results returned.

    Returns:
        Tuple containing:
        - List of matching file records (sorted by size descending).
        - Summary dictionary of file count and total size per extension.
    """
    root_dir = Path(root_dir).resolve()
    large_files: List[Dict[str, Any]] = []
    ext_summary: Dict[str, Dict[str, Any]] = {}

    for root, _, files in os.walk(root_dir):
        for f in files:
            file_path = Path(root) / f
            try:
                stat = file_path.stat()
                size = stat.st_size

                if size >= min_size_bytes:
                    ext = file_path.suffix.lower() or "no_extension"

                    record = {
                        "path": str(file_path),
                        "filename": file_path.name,
                        "extension": ext,
                        "size_bytes": size,
                        "size_readable": format_bytes(size),
                        "mtime": stat.st_mtime,
                    }
                    large_files.append(record)

                    if ext not in ext_summary:
                        ext_summary[ext] = {"count": 0, "total_size_bytes": 0}
                    ext_summary[ext]["count"] += 1
                    ext_summary[ext]["total_size_bytes"] += size

            except (OSError, PermissionError):
                continue

    # Sort descending by size
    large_files.sort(key=lambda x: int(x["size_bytes"]), reverse=True)

    if top_n and top_n > 0:
        large_files = large_files[:top_n]

    # Convert extension summary readable values
    ext_summary_formatted: Dict[str, Dict[str, Any]] = {}
    for ext, data in ext_summary.items():
        total_sz = data["total_size_bytes"]
        ext_summary_formatted[ext] = {
            "count": data["count"],
            "total_size_bytes": total_sz,
            "total_size_readable": format_bytes(total_sz),
        }

    return large_files, ext_summary_formatted


def format_report_console(
    large_files: List[Dict[str, Any]],
    ext_summary: Dict[str, Dict[str, Any]],
    min_size_bytes: int,
) -> str:
    """Format results for console output."""
    lines = []
    lines.append("=" * 70)
    readable_min = format_bytes(min_size_bytes)
    lines.append(f"LARGE FILE REPORT (Threshold: >= {readable_min})")
    lines.append("=" * 70)
    lines.append(f"Found {len(large_files)} files matching criteria.\n")

    lines.append("TOP FILES:")
    lines.append(f"{'Size':<12} | {'Extension':<10} | {'Path'}")
    lines.append("-" * 70)
    for f in large_files:
        sz_str = str(f["size_readable"])
        ext_str = str(f["extension"])
        lines.append(f"{sz_str:<12} | {ext_str:<10} | {f['path']}")

    lines.append("\nEXTENSION BREAKDOWN:")
    lines.append(f"{'Extension':<12} | {'Count':<8} | {'Total Size'}")
    lines.append("-" * 70)
    sorted_exts = sorted(
        ext_summary.items(),
        key=lambda x: int(x[1]["total_size_bytes"]),
        reverse=True,
    )
    for ext, data in sorted_exts:
        cnt = data["count"]
        tot_rd = data["total_size_readable"]
        lines.append(f"{ext:<12} | {cnt:<8} | {tot_rd}")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Scan directory for files exceeding size threshold."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "--path",
        "-p",
        required=True,
        type=Path,
        help="Directory path to scan",
    )
    parser.add_argument(
        "--min-size",
        "-s",
        default="100MB",
        help="Minimum size threshold (e.g. 100MB, 1GB)",
    )
    parser.add_argument(
        "--top",
        "-n",
        type=int,
        default=None,
        help="Limit output to top N files",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["console", "json", "csv"],
        default="console",
        help="Output format",
    )
    parser.add_argument("--output", "-o", type=Path, help="Output report file path")
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for large-file-finder."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    min_bytes = parse_size_string(parsed.min_size)
    large_files, ext_summary = scan_large_files(
        parsed.path, min_bytes, top_n=parsed.top
    )

    report_content = ""
    if parsed.format == "json":
        report_content = json.dumps(
            {
                "threshold_bytes": min_bytes,
                "threshold_readable": format_bytes(min_bytes),
                "files": large_files,
                "extension_summary": ext_summary,
            },
            indent=2,
        )

    elif parsed.format == "csv":
        writer_lines = ["Path,Filename,Extension,SizeBytes,SizeReadable"]
        for rec in large_files:
            p = rec["path"]
            fn = rec["filename"]
            ex = rec["extension"]
            sb = rec["size_bytes"]
            sr = rec["size_readable"]
            writer_lines.append(f'"{p}","{fn}","{ex}",{sb},"{sr}"')
        report_content = "\n".join(writer_lines)

    else:  # console
        report_content = format_report_console(large_files, ext_summary, min_bytes)

    if parsed.output:
        with open(parsed.output, "w", encoding="utf-8") as out_file:
            out_file.write(report_content)
        print(f"Report written to {parsed.output}")
    else:
        print(report_content)

    return 0


if __name__ == "__main__":
    sys.exit(main())
