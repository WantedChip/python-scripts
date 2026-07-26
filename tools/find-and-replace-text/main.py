"""Find and Replace Text.

Recursively performs find-and-replace across text files in a directory tree
with regex support, file extension filters, dry-run diff previews, and metrics.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import difflib
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


class FileReplaceResult:
    """Dataclass holding the replacement results for a single file."""

    def __init__(
        self,
        file_path: Path,
        replacement_count: int,
        diff_text: str,
        was_modified: bool,
    ) -> None:
        self.file_path: Path = file_path
        self.replacement_count: int = replacement_count
        self.diff_text: str = diff_text
        self.was_modified: bool = was_modified


def is_binary_file(file_path: Path, chunk_size: int = 1024) -> bool:
    """Heuristic check to determine if a file is binary."""
    try:
        with file_path.open("rb") as f:
            chunk = f.read(chunk_size)
            return b"\x00" in chunk
    except OSError:
        return True


def process_single_file(
    file_path: Path,
    search_pattern: str,
    replacement: str,
    is_regex: bool = False,
    dry_run: bool = True,
) -> Optional[FileReplaceResult]:
    """Processes a single file for search and replacement."""
    if is_binary_file(file_path):
        return None

    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Skip files that cannot be decoded as utf-8 text
        return None
    except OSError as e:
        print(f"Warning: Failed reading '{file_path}': {e}", file=sys.stderr)
        return None

    if is_regex:
        compiled_regex = re.compile(search_pattern)
        new_content, count = compiled_regex.subn(replacement, content)
    else:
        count = content.count(search_pattern)
        new_content = content.replace(search_pattern, replacement)

    if count == 0:
        return FileReplaceResult(file_path, 0, "", False)

    # Generate unified diff
    diff_lines = list(
        difflib.unified_diff(
            content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{file_path.name}",
            tofile=f"b/{file_path.name}",
        )
    )
    diff_text = "".join(diff_lines)

    if not dry_run:
        try:
            file_path.write_text(new_content, encoding="utf-8")
        except OSError as e:
            print(f"Error writing to '{file_path}': {e}", file=sys.stderr)
            return None

    return FileReplaceResult(
        file_path=file_path,
        replacement_count=count,
        diff_text=diff_text,
        was_modified=True,
    )


def find_and_replace_in_dir(
    directory: Path,
    search_pattern: str,
    replacement: str,
    extensions: Optional[Set[str]] = None,
    is_regex: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Recursively traverses directory performing find and replace.

    Returns summary metrics and file results.
    """
    if not directory.exists() or not directory.is_dir():
        msg = f"Target path '{directory}' is not a valid directory."
        raise ValueError(msg)

    total_scanned = 0
    modified_files_count = 0
    total_replacements = 0
    results: List[FileReplaceResult] = []

    # Clean extension set
    cleaned_exts: Optional[Set[str]] = None
    if extensions:
        cleaned_exts = {ext if ext.startswith(".") else f".{ext}" for ext in extensions}

    for path in directory.rglob("*"):
        if path.is_file():
            if cleaned_exts and path.suffix.lower() not in cleaned_exts:
                continue

            total_scanned += 1
            res = process_single_file(
                file_path=path,
                search_pattern=search_pattern,
                replacement=replacement,
                is_regex=is_regex,
                dry_run=dry_run,
            )

            if res and res.was_modified:
                modified_files_count += 1
                total_replacements += res.replacement_count
                results.append(res)

    return {
        "total_scanned": total_scanned,
        "modified_files_count": modified_files_count,
        "total_replacements": total_replacements,
        "results": results,
    }


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parses command line arguments."""
    parser = argparse.ArgumentParser(description="Find and Replace Text")
    parser.add_argument("directory", type=str, help="Target directory path")
    parser.add_argument(
        "--search",
        "-s",
        required=True,
        type=str,
        help="Text or regex to search for",
    )
    parser.add_argument(
        "--replace",
        "-r",
        required=True,
        type=str,
        help="Replacement text",
    )
    parser.add_argument(
        "--regex",
        action="store_true",
        help="Treat search pattern as a regular expression",
    )
    parser.add_argument(
        "--ext",
        nargs="+",
        default=None,
        help="Filter file extensions (e.g. .py .txt .md)",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Preview changes and diff without modifying files",
    )
    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI entry point."""
    parsed = parse_args(args)
    target_dir = Path(parsed.directory)

    ext_set = set(parsed.ext) if parsed.ext else None
    try:
        summary = find_and_replace_in_dir(
            directory=target_dir,
            search_pattern=parsed.search,
            replacement=parsed.replace,
            extensions=ext_set,
            is_regex=parsed.regex,
            dry_run=parsed.dry_run,
        )
    except (ValueError, OSError, re.error) as e:
        print(f"Error during find and replace: {e}", file=sys.stderr)
        return 1

    print("=" * 60)
    mode_str = "(DRY RUN)" if parsed.dry_run else ""
    print(f"FIND AND REPLACE METRICS {mode_str}")
    print("=" * 60)
    print(f"Total files scanned:    {summary['total_scanned']}")
    print(f"Files with matches:     {summary['modified_files_count']}")
    print(f"Total replacements:     {summary['total_replacements']}")
    print("-" * 60)

    if summary["results"]:
        print("\nDIFF PREVIEW / MODIFICATIONS:")
        for res in summary["results"]:
            msg = f"\n--- File: {res.file_path} ({res.replacement_count} matches)"
            print(msg)
            print(res.diff_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
