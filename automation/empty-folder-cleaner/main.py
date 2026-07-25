#!/usr/bin/env python3
"""
Empty Folder Cleaner CLI

Features:
- Recursive bottom-up directory traversal for empty folder cleanup in one pass
- Exclude specified ignored directories (e.g. .git, .venv, node_modules)
- Hidden and system file handling (.DS_Store, desktop.ini, Thumbs.db)
- Option to purge ignored junk files inside otherwise empty folders
- Dry-run preview and confirmation safety features
- Comprehensive deletion summary report
"""

import argparse
import fnmatch
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set, Tuple

DEFAULT_IGNORED_FILES = {".ds_store", "desktop.ini", "thumbs.db", ".gitignore"}
DEFAULT_EXCLUDED_FOLDERS = {
    ".git",
    ".svn",
    ".hg",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
}


@dataclass
class CleaningCandidate:
    """Represents a directory candidate for deletion."""

    directory: Path
    junk_files: List[Path] = field(default_factory=list)


def is_hidden_or_system(path: Path) -> bool:
    """
    Checks if a file or directory is hidden or system-generated.
    """
    name = path.name
    if name.startswith("."):
        return True
    if name.lower() in DEFAULT_IGNORED_FILES:
        return True
    return False


def is_folder_excluded(folder_path: Path, exclude_patterns: Set[str]) -> bool:
    """
    Checks if a folder matches any exclusion pattern or default excluded folder name.
    """
    name = folder_path.name.lower()
    for pat in exclude_patterns:
        if fnmatch.fnmatch(name, pat.lower()):
            return True
    return False


def find_empty_folders(
    root_dir: Path,
    ignore_hidden_files: bool = True,
    delete_junk_files: bool = False,
    exclude_patterns: Optional[Set[str]] = None,
) -> List[CleaningCandidate]:
    """
    Performs post-order (bottom-up) traversal to find empty directory candidates.
    """
    if not root_dir.exists() or not root_dir.is_dir():
        raise ValueError(
            f"Directory '{root_dir}' does not exist or is not a directory."
        )

    exclude_set = set(DEFAULT_EXCLUDED_FOLDERS)
    if exclude_patterns:
        exclude_set.update(exclude_patterns)

    candidates: List[CleaningCandidate] = []
    removed_set: Set[Path] = set()

    # Bottom-up traversal using os.walk(topdown=False)
    for current_root, dirs, files in os.walk(root_dir, topdown=False):
        current_path = Path(current_root)

        # Do not clean root folder itself
        if current_path == root_dir.resolve():
            continue

        if is_folder_excluded(current_path, exclude_set):
            continue

        # Check remaining subdirectories that were NOT marked for deletion
        rem_dirs = [
            current_path / d for d in dirs if (current_path / d) not in removed_set
        ]

        if rem_dirs:
            # Contains active non-empty subdirectories
            continue

        all_files = [current_path / f for f in files]
        junk_files: List[Path] = []

        if ignore_hidden_files:
            junk_files = [f for f in all_files if is_hidden_or_system(f)]
            non_junk_files = [f for f in all_files if not is_hidden_or_system(f)]
        else:
            non_junk_files = all_files

        if not non_junk_files:
            # If folder has no non-junk files
            if not junk_files or delete_junk_files:
                candidates.append(
                    CleaningCandidate(directory=current_path, junk_files=junk_files)
                )
                removed_set.add(current_path)

    return candidates


def execute_cleaning(
    candidates: List[CleaningCandidate], dry_run: bool = True
) -> Tuple[int, int]:
    """
    Deletes junk files and empty directories in the candidate list.

    Returns (num_folders_deleted, num_junk_files_deleted).
    """
    folders_deleted = 0
    files_deleted = 0

    for item in candidates:
        if not dry_run:
            # Remove junk files first
            for jf in item.junk_files:
                try:
                    if jf.exists():
                        jf.unlink()
                        files_deleted += 1
                except Exception as err:  # pylint: disable=broad-exception-caught
                    print(f"Failed to remove file '{jf}': {err}", file=sys.stderr)

            # Remove empty directory
            try:
                if item.directory.exists():
                    item.directory.rmdir()
                    folders_deleted += 1
            except Exception as err:  # pylint: disable=broad-exception-caught
                print(
                    f"Failed to remove directory '{item.directory}': {err}",
                    file=sys.stderr,
                )
        else:
            files_deleted += len(item.junk_files)
            folders_deleted += 1

    return folders_deleted, files_deleted


def main() -> None:
    """CLI entrypoint for empty folder cleaner."""
    parser = argparse.ArgumentParser(
        description=(
            "Recursively locate and remove empty directory trees with "
            "safety exclusions."
        )
    )
    parser.add_argument(
        "--dir",
        "-d",
        default=".",
        help="Root directory to clean (default: current directory)",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        help="Folder patterns to exclude from deletion (e.g. .git node_modules)",
    )
    parser.add_argument(
        "--keep-hidden-files",
        action="store_true",
        help="Do not treat hidden files (.DS_Store) as empty junk",
    )
    parser.add_argument(
        "--delete-junk",
        action="store_true",
        help="Delete hidden/junk files inside otherwise empty folders",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview empty folders without deleting",
    )
    parser.add_argument("--apply", action="store_true", help="Execute folder deletion")
    parser.add_argument(
        "--yes", "-y", action="store_true", help="Skip confirmation prompt"
    )

    args = parser.parse_args()
    root_dir = Path(args.dir).resolve()

    exclude_patterns = set(args.exclude) if args.exclude else set()
    ignore_hidden = not args.keep_hidden_files

    print(f"Scanning for empty folders in '{root_dir}'...")
    candidates = find_empty_folders(
        root_dir=root_dir,
        ignore_hidden_files=ignore_hidden,
        delete_junk_files=args.delete_junk,
        exclude_patterns=exclude_patterns,
    )

    if not candidates:
        print("No empty directories found.")
        return

    print(f"\n=== Found {len(candidates)} Empty Directory Candidate(s) ===")
    for item in candidates:
        has_j = bool(item.junk_files)
        junk_msg = f" (contains {len(item.junk_files)} junk file(s))" if has_j else ""
        print(f"  [EMPTY] {item.directory}{junk_msg}")

    if args.dry_run or not args.apply:
        print("\n[DRY RUN] No directories were deleted. Use --apply to execute.")
        return

    if not args.yes:
        msg = f"\nPermanently delete {len(candidates)} empty directory tree(s)? [y/N]: "
        confirm = input(msg)
        if confirm.lower() != "y":
            print("Operation cancelled.")
            return

    folders_del, files_del = execute_cleaning(candidates, dry_run=False)
    print("\n=== Deletion Summary Report ===")
    print(f"Successfully deleted {folders_del} empty folder(s).")
    if files_del > 0:
        print(f"Purged {files_del} leftover junk file(s).")


if __name__ == "__main__":
    main()
