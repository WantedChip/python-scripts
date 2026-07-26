"""Filename Sanitizer.

Bulk cleans filenames by normalizing Unicode accents, stripping illegal OS
characters, trimming trailing dots/spaces, and replacing whitespace.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional

WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}

# Illegal characters for Windows: <>:"/\|?* plus control chars (0-31)
WINDOWS_ILLEGAL_CHARS_REGEX = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Illegal characters for POSIX: / and null byte
POSIX_ILLEGAL_CHARS_REGEX = re.compile(r"[/[\x00]")


def remove_diacritics(text: str) -> str:
    """Decompose unicode characters and strip accent marks.

    Args:
        text: Input string.

    Returns:
        String with diacritics removed.
    """
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def sanitize_filename(
    filename: str,
    space_replacement: str = "_",
    lowercase: bool = False,
    strip_diacritics: bool = True,
    target_os: Optional[str] = None,
) -> str:
    """Sanitize a single filename.

    Args:
        filename: Base filename string (e.g. 'Crème Brûlée: 100%!.txt').
        space_replacement: Character to replace spaces with ('_', '-', or '').
        lowercase: Whether to convert to lowercase.
        strip_diacritics: Whether to remove unicode accents.
        target_os: 'windows', 'posix', or None (auto-detect OS).

    Returns:
        Cleaned, safe filename.
    """
    path_obj = Path(filename)
    stem, suffix = path_obj.stem, path_obj.suffix

    if strip_diacritics:
        stem = remove_diacritics(stem)

    if lowercase:
        stem = stem.lower()
        suffix = suffix.lower()

    # Determine target OS rules
    if target_os:
        current_os = target_os.lower()
    else:
        current_os = "windows" if os.name == "nt" else "posix"

    if current_os == "windows":
        stem = WINDOWS_ILLEGAL_CHARS_REGEX.sub("", stem)
        suffix = WINDOWS_ILLEGAL_CHARS_REGEX.sub("", suffix)
    else:
        stem = POSIX_ILLEGAL_CHARS_REGEX.sub("", stem)
        suffix = POSIX_ILLEGAL_CHARS_REGEX.sub("", suffix)

    # Replace spaces
    if space_replacement is not None and space_replacement != "none":
        stem = re.sub(r"\s+", space_replacement, stem)
    else:
        stem = re.sub(r"\s+", " ", stem)

    # Collapse multiple consecutive replacements (e.g. ___ -> _)
    if space_replacement in ("_", "-"):
        stem = re.sub(rf"\{space_replacement}+", space_replacement, stem)

    # Strip leading/trailing spaces/dots and hyphens/underscores if replaced
    strip_chars = " ."
    if space_replacement in ("_", "-"):
        strip_chars += space_replacement
    stem = stem.strip(strip_chars)

    if not stem:
        stem = "unnamed"

    # Check Windows reserved filenames
    if current_os == "windows" and stem.upper() in WINDOWS_RESERVED_NAMES:
        stem = f"{stem}_file"

    return f"{stem}{suffix}"


def sanitize_directory(
    target_dir: Path,
    space_replacement: str = "_",
    lowercase: bool = False,
    strip_diacritics: bool = True,
    recursive: bool = False,
    dry_run: bool = False,
) -> List[Dict[str, str]]:
    """Sanitize all files in target directory.

    Args:
        target_dir: Path to directory.
        space_replacement: '_', '-', or 'none'.
        lowercase: Lowercase flag.
        strip_diacritics: Diacritics flag.
        recursive: Whether to scan subfolders.
        dry_run: Simulate changes.

    Returns:
        List of rename operations (diff report).
    """
    target_dir = Path(target_dir).resolve()
    diff_report: List[Dict[str, str]] = []

    def process_folder(folder: Path) -> None:
        nonlocal diff_report
        # Process files in folder
        entries = sorted(list(folder.iterdir()), key=lambda p: p.name)
        for entry in entries:
            if entry.is_dir():
                if recursive:
                    process_folder(entry)
                continue

            old_name = entry.name
            new_name = sanitize_filename(
                old_name,
                space_replacement=space_replacement,
                lowercase=lowercase,
                strip_diacritics=strip_diacritics,
            )

            if old_name != new_name:
                new_path = folder / new_name

                # Prevent overwriting existing files
                counter = 1
                while new_path.exists() and new_path != entry:
                    stem = Path(new_name).stem
                    ext = Path(new_name).suffix
                    new_path = folder / f"{stem}_{counter}{ext}"
                    counter += 1

                record = {
                    "folder": str(folder),
                    "old_name": old_name,
                    "new_name": new_path.name,
                    "old_path": str(entry),
                    "new_path": str(new_path),
                    "status": "dry_run" if dry_run else "renamed",
                }

                if not dry_run:
                    try:
                        entry.rename(new_path)
                    except OSError as e:
                        record["status"] = f"failed: {e}"

                diff_report.append(record)

    process_folder(target_dir)
    return diff_report


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Bulk sanitize filenames in a directory."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "--path",
        "-p",
        required=True,
        type=Path,
        help="Target directory path",
    )
    parser.add_argument(
        "--space-replacement",
        "-s",
        choices=["_", "-", "none"],
        default="_",
        help="Space replacement character",
    )
    parser.add_argument(
        "--lowercase",
        "-l",
        action="store_true",
        help="Convert filenames to lowercase",
    )
    parser.add_argument(
        "--no-diacritics",
        action="store_false",
        dest="strip_diacritics",
        help="Disable diacritics stripping",
    )
    parser.add_argument(
        "--recursive",
        "-r",
        action="store_true",
        help="Process subdirectories recursively",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview proposed changes without renaming files",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for filename-sanitizer."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    diffs = sanitize_directory(
        target_dir=parsed.path,
        space_replacement=parsed.space_replacement,
        lowercase=parsed.lowercase,
        strip_diacritics=parsed.strip_diacritics,
        recursive=parsed.recursive,
        dry_run=parsed.dry_run,
    )

    msg = (
        f"Sanitization preview/execution finished "
        f"({len(diffs)} files modified/proposed):"
    )
    print(msg)
    for d in diffs:
        print(f"  [ {d['status']} ] {d['old_name']} -> {d['new_name']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
