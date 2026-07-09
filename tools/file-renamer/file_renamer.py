#!/usr/bin/env python3
"""Bulk File Renamer with Undo capability.

This script provides bulk file renaming functionality with support for:
- Filtering files by glob pattern and exclusions.
- Recursive processing.
- Renaming pipeline: Casing/Spaces -> Date Cleanup -> Regex -> Numbering.
- Pre-flight collision checks (many-to-one and external collisions).
- 2-Phase Renaming to safely handle swaps, chains, and case-only changes.
- Rollback logs and Undo mode with partial undo safety.
"""

import argparse
import datetime
import fnmatch
import json
import os
import re
import sys
import uuid
from typing import Dict, List, Optional, Tuple

# pylint: disable=broad-exception-caught,too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-nested-blocks,raise-missing-from


def normcase_fs(path: str) -> str:
    """Normalize case of path based on filesystem case-sensitivity.

    Args:
        path: Path string.

    Returns:
        Normalized path string.
    """
    path_abs = os.path.abspath(path)
    if sys.platform in ("win32", "darwin"):
        return path_abs.lower()
    return path_abs


def parse_args(args_list: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments.

    Args:
        args_list: Optional list of command line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Bulk File Renamer with Transaction Safety and Undo support."
    )
    parser.add_argument(
        "-d", "--dir", default=".", help="Target directory to scan (default: .)"
    )
    parser.add_argument(
        "--match", default="*", help="Glob pattern to match files (default: *)"
    )
    parser.add_argument(
        "--exclude", default=None, help="Glob pattern to exclude files (default: None)"
    )
    parser.add_argument(
        "-r", "--recursive", action="store_true", help="Scan subdirectories recursively"
    )

    # Renaming modes
    parser.add_argument(
        "--regex-find", default=None, help="Regex pattern to find in file stem"
    )
    parser.add_argument(
        "--regex-replace", default=None, help="Replacement string for regex"
    )

    parser.add_argument(
        "--number", action="store_true", help="Enable sequential numbering"
    )
    parser.add_argument(
        "--number-start", type=int, default=1, help="Starting number (default: 1)"
    )
    parser.add_argument(
        "--number-step",
        type=int,
        default=1,
        help="Increment step for numbering (default: 1)",
    )
    parser.add_argument(
        "--number-padding",
        type=int,
        default=3,
        help="Zero padding width for numbers (default: 3)",
    )
    parser.add_argument(
        "--number-format",
        default="{name}_{num}",
        help="Format for numbering (default: {name}_{num})",
    )
    parser.add_argument(
        "--sort",
        choices=["name", "mtime", "size"],
        default="name",
        help="Sorting method before numbering (default: name)",
    )

    parser.add_argument(
        "--clean-dates",
        action="store_true",
        help="Clean and normalize dates in filenames to YYYY-MM-DD",
    )
    parser.add_argument(
        "--date-format",
        choices=["DMY", "MDY", "YMD"],
        default="YMD",
        help="Format to resolve ambiguous date structures (default: YMD)",
    )

    parser.add_argument(
        "--lower", action="store_true", help="Convert stem to lowercase"
    )
    parser.add_argument(
        "--upper", action="store_true", help="Convert stem to uppercase"
    )
    parser.add_argument(
        "--replace-spaces",
        nargs="?",
        const="_",
        default=None,
        help="Replace spaces with optional char (default: '_')",
    )

    # Operational
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview proposed changes without execution",
    )
    parser.add_argument(
        "--force", action="store_true", help="Skip user confirmation prompt"
    )
    parser.add_argument(
        "--history-file",
        default=None,
        help="Path to history file (default: .rename_history.json)",
    )
    parser.add_argument(
        "--undo", action="store_true", help="Rollback the last rename operation"
    )

    args = parser.parse_args(args_list)

    if args.lower and args.upper:
        parser.error("Arguments --lower and --upper are mutually exclusive")

    if args.number:
        # Validate format string
        try:
            args.number_format.format(name="test", num="001")
        except Exception as e:
            parser.error(f"Invalid --number-format '{args.number_format}': {e}")

    return args


def clean_dates_in_stem(stem: str, date_format: str) -> str:
    """Clean and normalize dates in stem to YYYY-MM-DD.

    Args:
        stem: The filename stem.
        date_format: The format choice to resolve ambiguity ('DMY', 'MDY', 'YMD').

    Returns:
        The normalized filename stem.
    """

    def replace_year_first(match: re.Match[str]) -> str:
        y_str, m_str, d_str = match.groups()
        y, m, d = int(y_str), int(m_str), int(d_str)
        if 1 <= m <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{m:02d}-{d:02d}"
        return str(match.group(0))

    def replace_year_last(match: re.Match[str]) -> str:
        part1_str, part2_str, y_str = match.groups()
        p1, p2, y = int(part1_str), int(part2_str), int(y_str)
        if date_format == "MDY":
            m, d = p1, p2
        else:  # DMY or YMD (default to DMY for year-last)
            d, m = p1, p2
        if 1 <= m <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{m:02d}-{d:02d}"
        return str(match.group(0))

    # Year-first: e.g., 2023-05-12, 2023.5.2, 2023_05_12, 2023 05 12
    stem = re.sub(
        r"(?<!\d)(\d{4})[-._\s](\d{1,2})[-._\s](\d{1,2})(?!\d)",
        replace_year_first,
        stem,
    )
    # Year-last: e.g., 12-05-2023, 5.2.2023, 12_05_2023, 12 05 2023
    stem = re.sub(
        r"(?<!\d)(\d{1,2})[-._\s](\d{1,2})[-._\s](\d{4})(?!\d)", replace_year_last, stem
    )
    return stem


def collect_files(
    target_dir: str,
    match_pattern: str,
    exclude_pattern: Optional[str],
    recursive: bool,
    history_file_abs: str,
) -> List[str]:
    """Collect all matching file paths in target directory.

    Args:
        target_dir: Base directory to scan.
        match_pattern: Glob pattern to include files.
        exclude_pattern: Glob pattern to exclude files.
        recursive: Whether to scan recursively.
        history_file_abs: Absolute path to the history file to exclude.

    Returns:
        Sorted list of absolute file paths.
    """
    matched_files = []
    script_abs = os.path.abspath(__file__)

    if recursive:
        for root, _, files in os.walk(target_dir):
            for file in files:
                full_path = os.path.abspath(os.path.join(root, file))
                # Skip history file and the script itself
                if full_path in (history_file_abs, script_abs):
                    continue
                if fnmatch.fnmatch(file, match_pattern):
                    if exclude_pattern and fnmatch.fnmatch(file, exclude_pattern):
                        continue
                    matched_files.append(full_path)
    else:
        try:
            for entry in os.scandir(target_dir):
                if entry.is_file():
                    full_path = os.path.abspath(entry.path)
                    # Skip history file and the script itself
                    if full_path in (history_file_abs, script_abs):
                        continue
                    if fnmatch.fnmatch(entry.name, match_pattern):
                        if exclude_pattern and fnmatch.fnmatch(
                            entry.name, exclude_pattern
                        ):
                            continue
                        matched_files.append(full_path)
        except OSError as e:
            sys.stderr.write(f"Error scanning directory '{target_dir}': {e}\n")
            sys.exit(1)

    return matched_files


def is_no_op(src: str, dest: str) -> bool:
    """Check if rename is a case-sensitive no-op.

    Args:
        src: Source path.
        dest: Destination path.

    Returns:
        True if paths are identical, False otherwise.
    """
    return os.path.abspath(src) == os.path.abspath(dest)


def validate_renames(rename_list: List[Tuple[str, str]]) -> List[str]:
    """Pre-flight collision validation checks.

    Args:
        rename_list: List of (source, destination) absolute paths.

    Returns:
        List of conflict description strings.
    """
    src_set_normalized = {normcase_fs(src) for src, _ in rename_list}

    dest_normalized_to_srcs: Dict[str, List[Tuple[str, str]]] = {}
    for src, dest in rename_list:
        dest_norm = normcase_fs(dest)
        dest_normalized_to_srcs.setdefault(dest_norm, []).append((src, dest))

    conflicts = []

    # Check 1: Many-to-one collisions
    for dest_norm, items in dest_normalized_to_srcs.items():
        if len(items) > 1:
            src_paths = [src for src, _ in items]
            dest_paths = [dest for _, dest in items]
            conflicts.append(
                f"Many-to-one collision: {len(items)} files want to "
                "rename to conflicting destinations: "
                f"sources={src_paths}, destinations={dest_paths}"
            )

    # Check 2: External collisions
    for src, dest in rename_list:
        dest_abs = os.path.abspath(dest)
        dest_normalized = normcase_fs(dest_abs)
        if os.path.exists(dest_abs):
            is_same = False
            try:
                if os.path.samefile(src, dest_abs):
                    is_same = True
            except OSError:
                pass
            if not is_same and dest_normalized not in src_set_normalized:
                conflicts.append(
                    f"External collision: Target '{dest}' already exists on disk "
                    f"and is not in the source rename list (from '{src}')"
                )

    return conflicts


def print_preview_table(
    rename_list: List[Tuple[str, str]], target_dir: str, _conflicts: List[str]
) -> None:
    """Print clean tabular format of proposed changes.

    Args:
        rename_list: List of (source, destination) absolute paths.
        target_dir: Base target directory.
        conflicts: List of conflict messages.
    """
    headers = ["Original Path", "Proposed Path", "Status"]
    rows = []

    # Identify conflict destinations (case-insensitive)
    # Re-evaluate logic to label each row
    src_set_normalized = {normcase_fs(src) for src, _ in rename_list}
    dest_normalized_to_srcs: Dict[str, List[str]] = {}
    for src, dest in rename_list:
        dest_norm = normcase_fs(dest)
        dest_normalized_to_srcs.setdefault(dest_norm, []).append(src)

    for src, dest in rename_list:
        src_rel = os.path.relpath(src, target_dir)
        dest_rel = os.path.relpath(dest, target_dir)

        dest_norm = normcase_fs(dest)
        dest_abs = os.path.abspath(dest)

        # Determine status
        status = "OK"
        is_same = False
        try:
            if os.path.exists(dest_abs) and os.path.samefile(src, dest_abs):
                is_same = True
        except OSError:
            pass

        if len(dest_normalized_to_srcs.get(dest_norm, [])) > 1:
            status = "COLLISION (Many-to-One)"
        elif (
            os.path.exists(dest_abs)
            and not is_same
            and dest_norm not in src_set_normalized
        ):
            status = "COLLISION (External)"
        elif is_no_op(src, dest):
            status = "NO_CHANGE"

        rows.append((src_rel, dest_rel, status))

    col_widths = [len(h) for h in headers]
    for row in rows:
        col_widths[0] = max(col_widths[0], len(row[0]))
        col_widths[1] = max(col_widths[1], len(row[1]))
        col_widths[2] = max(col_widths[2], len(row[2]))

    fmt = f"{{:<{col_widths[0]}}}  {{:<{col_widths[1]}}}  {{:<{col_widths[2]}}}"
    print(fmt.format(*headers))
    print("-" * (sum(col_widths) + 4))
    for row in rows:
        print(fmt.format(*row))


def execute_2phase_rename(rename_list: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """Execute rename list using 2-phase approach for transaction safety.

    Args:
        rename_list: List of (source, destination) absolute paths.

    Returns:
        List of successfully renamed (source, destination) pairs.
    """
    phase1_done = []  # list of (src, temp_path, dest)

    try:
        for src, dest in rename_list:
            parent_dir = os.path.dirname(src)
            base_name = os.path.basename(src)
            temp_name = f"{base_name}.{uuid.uuid4().hex}.tmp_rename"
            temp_path = os.path.join(parent_dir, temp_name)

            while os.path.exists(temp_path):
                temp_name = f"{base_name}.{uuid.uuid4().hex}.tmp_rename"
                temp_path = os.path.join(parent_dir, temp_name)

            os.rename(src, temp_path)
            phase1_done.append((src, temp_path, dest))
    except Exception as e:
        # Phase 1 failed midway! Revert successfully completed temp renames
        sys.stderr.write(
            f"Phase 1 renaming failed midway: {e}. Reverting completed changes...\n"
        )
        for src_path, tmp_path, _ in reversed(phase1_done):
            try:
                os.rename(tmp_path, src_path)
            except Exception as revert_err:
                sys.stderr.write(
                    f"Failed to revert temp rename from '{tmp_path}' "
                    f"back to '{src_path}': {revert_err}\n"
                )
        raise RuntimeError(f"Phase 1 failure: {e}")

    phase2_done = []
    try:
        for src, temp_path, dest in phase1_done:
            # Ensure target parent directory exists (needed in case renaming
            # moves files, though our logic keeps them in same dir)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            os.rename(temp_path, dest)
            phase2_done.append((src, dest))
    except Exception as e:
        # Phase 2 failed midway!
        # Revert successfully completed final renames back to temp files
        sys.stderr.write(
            f"Phase 2 renaming failed midway: {e}. Reverting to original files...\n"
        )
        for src_path, dest_path in reversed(phase2_done):
            # Find matching temp path
            for s, t, _ in phase1_done:
                if s == src_path:
                    try:
                        os.rename(dest_path, t)
                    except Exception as revert_err:
                        sys.stderr.write(
                            f"Failed to rename '{dest_path}' back to temp "
                            f"'{t}': {revert_err}\n"
                        )
                    break
        # Revert all temp files back to source paths
        for src_path, tmp_path, _ in reversed(phase1_done):
            if os.path.exists(tmp_path):
                try:
                    os.rename(tmp_path, src_path)
                except Exception as revert_err:
                    sys.stderr.write(
                        f"Failed to revert temp '{tmp_path}' back to source "
                        f"'{src_path}': {revert_err}\n"
                    )
        raise RuntimeError(f"Phase 2 failure: {e}")

    return phase2_done


def execute_undo(history_file_path: str, target_dir: str) -> None:
    """Load history file and perform rollback of renames in reverse order.

    Args:
        history_file_path: Path to the JSON history log file.
        target_dir: Base target directory.
    """
    if not os.path.exists(history_file_path):
        sys.stderr.write(f"Error: History file '{history_file_path}' does not exist.\n")
        sys.exit(1)

    try:
        with open(history_file_path, "r", encoding="utf-8") as f:
            history_data = json.load(f)
    except Exception as e:
        sys.stderr.write(f"Error reading history file '{history_file_path}': {e}\n")
        sys.exit(1)

    if history_data.get("undone", False):
        print("History log shows this rename operation has already been undone.")
        sys.exit(0)

    renames = history_data.get("renames", [])
    if not renames:
        print("No renames recorded in history log.")
        sys.exit(0)

    # Resolve relative paths to absolute paths
    undo_pairs = []
    for r in renames:
        src_abs = os.path.abspath(os.path.join(target_dir, r["src"]))
        dest_abs = os.path.abspath(os.path.join(target_dir, r["dest"]))
        undo_pairs.append((src_abs, dest_abs))

    # Pre-undo validations
    # 1. Verify all dest files (current files on disk) exist
    missing_files = []
    for _, dest_abs in undo_pairs:
        if not os.path.exists(dest_abs):
            missing_files.append(dest_abs)

    # 2. Verify all src files (original paths to restore) do not exist
    # (unless part of the undo plan)
    dest_set_normalized = {normcase_fs(d) for _, d in undo_pairs}
    existing_srcs = []
    for src_abs, dest_abs in undo_pairs:
        if os.path.exists(src_abs):
            # If src_abs and dest_abs refer to the same filesystem object
            # (case-only change), it's the same file, so skip conflict warning
            is_same = False
            try:
                if os.path.samefile(src_abs, dest_abs):
                    is_same = True
            except OSError:
                pass
            if is_same:
                continue
            src_norm = normcase_fs(src_abs)
            if src_norm not in dest_set_normalized:
                existing_srcs.append(src_abs)

    if missing_files or existing_srcs:
        if missing_files:
            sys.stderr.write(
                "Undo validation failed: The following files to be undone "
                "do not exist on disk:\n"
            )
            for fpath in missing_files:
                sys.stderr.write(f"  - {fpath}\n")
        if existing_srcs:
            sys.stderr.write(
                "Undo validation failed: The following original paths "
                "already exist on disk (and are not part of the undo plan):\n"
            )
            for fpath in existing_srcs:
                sys.stderr.write(f"  - {fpath}\n")
        sys.exit(1)

    # Perform undo in reverse order
    undo_list = list(reversed(undo_pairs))

    temp_renames = []  # list of (src, temp_path, dest)

    try:
        for src, dest in undo_list:
            # Here dest is current file, src is the original file we want to restore to.
            # We rename dest (current) -> temp
            parent_dir = os.path.dirname(dest)
            base_name = os.path.basename(dest)
            temp_name = f"{base_name}.{uuid.uuid4().hex}.tmp_rename"
            temp_path = os.path.join(parent_dir, temp_name)

            while os.path.exists(temp_path):
                temp_name = f"{base_name}.{uuid.uuid4().hex}.tmp_rename"
                temp_path = os.path.join(parent_dir, temp_name)

            os.rename(dest, temp_path)
            temp_renames.append((src, temp_path, dest))
    except Exception as e:
        sys.stderr.write(f"Undo Phase 1 failed midway: {e}. Reverting temp files...\n")
        for _, temp_path, dest in reversed(temp_renames):
            try:
                os.rename(temp_path, dest)
            except Exception as revert_err:
                sys.stderr.write(
                    f"Failed to revert temp rename from '{temp_path}' "
                    f"back to '{dest}': {revert_err}\n"
                )
        sys.exit(1)

    # Phase 2: Rename temp files to original src paths
    failed_index = -1
    for idx, (src, temp_path, dest) in enumerate(temp_renames):
        try:
            os.makedirs(os.path.dirname(src), exist_ok=True)
            os.rename(temp_path, src)
        except Exception as e:
            failed_index = idx
            sys.stderr.write(
                f"Failed to rename temp file '{temp_path}' to target '{src}': {e}\n"
            )
            break

    if failed_index != -1:
        # Phase 2 failed midway!
        # Restore remaining temp files back to their current dest paths
        sys.stderr.write(
            "Undo Phase 2 failed midway. Restoring remaining temp files...\n"
        )
        for idx in range(failed_index, len(temp_renames)):
            _, temp_path, dest = temp_renames[idx]
            try:
                os.rename(temp_path, dest)
            except Exception as revert_err:
                sys.stderr.write(
                    f"Critical: Failed to restore temp file '{temp_path}' "
                    f"back to '{dest}': {revert_err}\n"
                )

        # Reconstruct remaining uncompleted forward renames
        remaining_forward = []
        for idx in range(failed_index, len(temp_renames)):
            src, _, dest = temp_renames[idx]
            remaining_forward.append({"src": src, "dest": dest})
        # Reverse to restore original forward order
        remaining_forward.reverse()

        # Convert back to relative paths for history file
        remaining_history_renames = []
        for item in remaining_forward:
            rel_src = os.path.relpath(item["src"], target_dir).replace("\\", "/")
            rel_dest = os.path.relpath(item["dest"], target_dir).replace("\\", "/")
            remaining_history_renames.append({"src": rel_src, "dest": rel_dest})

        history_data["renames"] = remaining_history_renames
        try:
            with open(history_file_path, "w", encoding="utf-8") as f:
                json.dump(history_data, f, indent=2)
            sys.stderr.write(
                "Updated history file with remaining uncompleted renames.\n"
            )
        except Exception as save_err:
            sys.stderr.write(f"Critical: Failed to update history file: {save_err}\n")
        sys.exit(1)

    # Successfully undone everything!
    history_data["undone"] = True
    try:
        with open(history_file_path, "w", encoding="utf-8") as f:
            json.dump(history_data, f, indent=2)

        undone_file_path = history_file_path + ".undone"
        if os.path.exists(undone_file_path):
            os.remove(undone_file_path)
        os.rename(history_file_path, undone_file_path)
        print("Undo operation completed successfully.")
    except Exception as save_err:
        sys.stderr.write(
            f"Warning: Failed to save/rename history log to .undone: {save_err}\n"
        )
        sys.exit(0)


def main(args_list: Optional[List[str]] = None) -> None:
    """Main script entry point."""
    args = parse_args(args_list)

    target_dir = os.path.abspath(args.dir)
    if not os.path.isdir(target_dir):
        sys.stderr.write(f"Error: Target directory '{target_dir}' does not exist.\n")
        sys.exit(1)

    # Determine history file path
    if args.history_file is None:
        history_file_path = os.path.abspath(
            os.path.join(target_dir, ".rename_history.json")
        )
    else:
        history_file_path = os.path.abspath(args.history_file)

    # Run Undo mode if requested
    if args.undo:
        execute_undo(history_file_path, target_dir)
        sys.exit(0)

    # Collect matching files
    matched_files = collect_files(
        target_dir, args.match, args.exclude, args.recursive, history_file_path
    )

    if not matched_files:
        print("No files matched the criteria.")
        sys.exit(0)

    # Sort files
    if args.sort == "mtime":
        matched_files.sort(
            key=lambda p: (os.path.getmtime(p), os.path.relpath(p, target_dir))
        )
    elif args.sort == "size":
        matched_files.sort(
            key=lambda p: (os.path.getsize(p), os.path.relpath(p, target_dir))
        )
    else:  # 'name'
        matched_files.sort(key=lambda p: os.path.relpath(p, target_dir))

    # Compile regex replacement if specified
    regex_replace = args.regex_replace if args.regex_replace is not None else ""

    # Generate renaming plan
    rename_list = []
    for i, filepath in enumerate(matched_files):
        dir_name = os.path.dirname(filepath)
        base_name = os.path.basename(filepath)
        stem, ext = os.path.splitext(base_name)

        # 1. Casing/Spaces
        if args.lower:
            stem = stem.lower()
        elif args.upper:
            stem = stem.upper()
        if args.replace_spaces is not None:
            stem = stem.replace(" ", args.replace_spaces)

        # 2. Date Cleanup
        if args.clean_dates:
            stem = clean_dates_in_stem(stem, args.date_format)

        # 3. Regex Replace
        if args.regex_find:
            try:
                stem = re.sub(args.regex_find, regex_replace, stem)
            except re.error as e:
                sys.stderr.write(
                    f"Error: Invalid regular expression pattern "
                    f"'{args.regex_find}': {e}\n"
                )
                sys.exit(1)

        # 4. Numbering
        if args.number:
            num = args.number_start + i * args.number_step
            num_str = f"{num:0{args.number_padding}d}"
            try:
                stem = args.number_format.format(name=stem, num=num_str)
            except KeyError as e:
                sys.stderr.write(
                    f"Error: Invalid --number-format key: {e}. "
                    "Only {name} and {num} are supported.\n"
                )
                sys.exit(1)

        new_filename = stem + ext
        dest_path = os.path.join(dir_name, new_filename)
        rename_list.append((filepath, dest_path))

    # Filter out no-op renames
    rename_list = [(src, dest) for src, dest in rename_list if not is_no_op(src, dest)]

    if not rename_list:
        print("No files need renaming (all planned renames are no-ops).")
        sys.exit(0)

    # Pre-flight validation checks
    conflicts = validate_renames(rename_list)

    if args.dry_run:
        print("Proposed changes preview:")
        print_preview_table(rename_list, target_dir, conflicts)
        if conflicts:
            sys.stderr.write("\nValidation errors detected during dry-run:\n")
            for conf in conflicts:
                sys.stderr.write(f"  - {conf}\n")
            sys.exit(1)
        sys.exit(0)

    if conflicts:
        sys.stderr.write("Validation errors detected. Renaming aborted:\n")
        for conf in conflicts:
            sys.stderr.write(f"  - {conf}\n")
        sys.exit(1)

    # Prompt user for confirmation if not forced
    if not args.force:
        print("Proposed changes:")
        print_preview_table(rename_list, target_dir, [])
        confirm = input("\nAre you sure you want to proceed with the renaming? (y/N): ")
        if confirm.lower() not in ["y", "yes"]:
            print("Renaming aborted by user.")
            sys.exit(0)

    # Execute 2-phase rename
    try:
        executed_renames = execute_2phase_rename(rename_list)
    except RuntimeError as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)

    # Save history log
    history_data = {
        "base_dir": target_dir.replace("\\", "/"),
        "timestamp": datetime.datetime.now(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "command": " ".join(sys.argv),
        "renames": [
            {
                "src": os.path.relpath(src, target_dir).replace("\\", "/"),
                "dest": os.path.relpath(dest, target_dir).replace("\\", "/"),
            }
            for src, dest in executed_renames
        ],
        "undone": False,
    }

    try:
        with open(history_file_path, "w", encoding="utf-8") as f:
            json.dump(history_data, f, indent=2)
        print(f"Renaming completed. History saved to '{history_file_path}'.")
    except Exception as e:
        sys.stderr.write(
            f"Warning: Renaming completed, but failed to save history file: {e}\n"
        )


if __name__ == "__main__":
    main()
