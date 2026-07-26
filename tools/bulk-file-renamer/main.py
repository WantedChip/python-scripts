#!/usr/bin/env python3
"""Bulk File Renamer CLI.

Features:
- Regex pattern matching and substitution
- Sequential numbering with customizable formatting
- Case formatting (lower, upper, title, camel, snake)
- Prefix and suffix addition
- Collision detection before renaming
- Interactive preview and dry-run mode
- Undo manifest logging and rollback support
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-many-return-statements

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class RenamePlanItem:
    """Data class representing a single proposed file rename action."""

    source: Path
    target: Path
    matched: bool
    status: str = "PENDING"


def apply_case_format(text: str, case_style: Optional[str]) -> str:
    """Transforms text into requested case style.

    Supported styles: lower, upper, title, camel, snake.
    """
    if not case_style:
        return text

    style = case_style.lower()
    if style == "lower":
        return text.lower()
    if style == "upper":
        return text.upper()
    if style == "title":
        return text.title()
    if style == "snake":
        pat = r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\b)|[0-9]+"
        words = re.findall(pat, text)
        return "_".join(w.lower() for w in words) if words else text.lower()
    if style == "camel":
        pat = r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\b)|[0-9]+"
        words = re.findall(pat, text)
        if not words:
            return text
        res = words[0].lower() + "".join(w.capitalize() for w in words[1:])
        return str(res)
    return text


def build_rename_plan(
    directory: Path,
    match_pattern: str = r".*",
    replace_pattern: str = r"\g<0>",
    prefix: str = "",
    suffix: str = "",
    number_start: Optional[int] = None,
    number_step: int = 1,
    number_format: str = "{:03d}",
    case_style: Optional[str] = None,
    recursive: bool = False,
) -> List[RenamePlanItem]:
    """Builds a list of proposed file rename operations based on rules."""
    if not directory.exists() or not directory.is_dir():
        err_msg = f"Directory '{directory}' does not exist or is not a dir."
        raise ValueError(err_msg)

    regex = re.compile(match_pattern)
    plan: List[RenamePlanItem] = []

    if recursive:
        all_files = list(directory.rglob("*"))
    else:
        all_files = list(directory.iterdir())

    files = [f for f in all_files if f.is_file()]
    files.sort(key=lambda p: p.name)

    seq = number_start if number_start is not None else 0

    for filepath in files:
        stem = filepath.stem
        ext = filepath.suffix
        filename = filepath.name

        match = regex.search(filename)
        if not match:
            continue

        # Check if matching stem or full filename
        if regex.search(stem):
            new_stem = regex.sub(replace_pattern, stem)
            new_ext = ext
        else:
            new_name = regex.sub(replace_pattern, filename)
            new_path = Path(new_name)
            new_stem = new_path.stem
            new_ext = new_path.suffix

        # Case formatting
        if case_style:
            new_stem = apply_case_format(new_stem, case_style)

        # Prefix and suffix
        new_stem = f"{prefix}{new_stem}{suffix}"

        # Sequential numbering
        if number_start is not None:
            num_str = number_format.format(seq)
            new_stem = f"{new_stem}_{num_str}"
            seq += number_step

        target_name = f"{new_stem}{new_ext}"
        target_path = filepath.parent / target_name

        matched = filename != target_name
        item = RenamePlanItem(source=filepath, target=target_path, matched=matched)
        plan.append(item)

    return plan


def check_collisions(plan: List[RenamePlanItem]) -> List[str]:
    """Validates plan for collisions (target file issues / duplicates)."""
    collisions: List[str] = []
    seen_targets: Dict[Path, Path] = {}

    for item in plan:
        if not item.matched:
            continue

        # Target file already exists on disk and is not part of source set
        if item.target.exists() and item.target != item.source:
            if not any(other.source == item.target for other in plan):
                c_msg = (
                    f"Target file exists: '{item.target.name}' "
                    f"(from '{item.source.name}')"
                )
                collisions.append(c_msg)

        # Multiple sources map to exact same target path
        if item.target in seen_targets:
            prev_source = seen_targets[item.target]
            c_msg = (
                f"Duplicate target '{item.target.name}' mapped from "
                f"'{prev_source.name}' and '{item.source.name}'"
            )
            collisions.append(c_msg)
        else:
            seen_targets[item.target] = item.source

    return collisions


def execute_rename_plan(
    plan: List[RenamePlanItem], manifest_path: Optional[Path] = None
) -> List[Tuple[str, str]]:
    """Executes rename operations and writes an undo manifest if specified."""
    executed: List[Tuple[str, str]] = []

    for item in plan:
        if not item.matched:
            continue

        try:
            item.target.parent.mkdir(parents=True, exist_ok=True)
            item.source.rename(item.target)
            item.status = "SUCCESS"
            src_str = str(item.source.resolve())
            tgt_str = str(item.target.resolve())
            executed.append((src_str, tgt_str))
        except (OSError, IOError) as err:
            item.status = f"FAILED: {err}"

    if manifest_path and executed:
        manifest_data = {
            "renames": [{"source": src, "target": tgt} for src, tgt in executed]
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

    return executed


def rollback_from_manifest(manifest_path: Path) -> List[Tuple[str, str]]:
    """Rolls back previous rename operations using undo manifest JSON file."""
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest file '{manifest_path}' not found.")

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    renames = data.get("renames", [])
    restored: List[Tuple[str, str]] = []

    # Process in reverse order to handle chained renames correctly
    for item in reversed(renames):
        src_path = Path(item["source"])
        tgt_path = Path(item["target"])

        if tgt_path.exists():
            tgt_path.rename(src_path)
            restored.append((str(tgt_path), str(src_path)))

    return restored


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = (
        "Bulk file renamer CLI with regex, case formatting, numbering, "
        "collision check, and undo support."
    )
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "--dir",
        "-d",
        default=".",
        help="Target directory (default: current directory)",
    )
    parser.add_argument(
        "--match",
        "-m",
        default=r".*",
        help="Regex pattern to match filenames",
    )
    parser.add_argument(
        "--replace",
        "-r",
        default=r"\g<0>",
        help="Replacement pattern (supports regex backreferences)",
    )
    parser.add_argument(
        "--prefix", default="", help="Prefix to prepend to filename stem"
    )
    parser.add_argument(
        "--suffix", default="", help="Suffix to append to filename stem"
    )
    parser.add_argument(
        "--number-start",
        type=int,
        default=None,
        help="Start sequential numbering",
    )
    parser.add_argument(
        "--number-step",
        type=int,
        default=1,
        help="Step increment for numbering",
    )
    parser.add_argument(
        "--number-format",
        default="{:03d}",
        help="Python string format for numbers (e.g. {:03d})",
    )
    parser.add_argument(
        "--case",
        choices=["lower", "upper", "title", "camel", "snake"],
        help="Case transformation style",
    )
    parser.add_argument(
        "--recursive",
        "-R",
        action="store_true",
        help="Recursively process subdirectories",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview renames without executing",
    )
    parser.add_argument(
        "--apply", action="store_true", help="Perform actual rename operations"
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompt when applying",
    )
    parser.add_argument(
        "--manifest",
        default="rename_manifest.json",
        help="Path to save undo manifest JSON",
    )
    parser.add_argument(
        "--undo",
        action="store_true",
        help="Undo previous rename using manifest file",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entrypoint for bulk file renamer."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    if parsed.undo:
        manifest_file = Path(parsed.manifest)
        try:
            rolled_back = rollback_from_manifest(manifest_file)
            msg = f"Undo completed! Rolled back {len(rolled_back)} file(s)."
            print(msg)
            for tgt, src in rolled_back:
                print(f"  Restored: {Path(tgt).name} -> {Path(src).name}")
        except (OSError, IOError, ValueError, json.JSONDecodeError) as e:
            print(f"Error during undo: {e}", file=sys.stderr)
            return 1
        return 0

    target_dir = Path(parsed.dir)
    plan = build_rename_plan(
        directory=target_dir,
        match_pattern=parsed.match,
        replace_pattern=parsed.replace,
        prefix=parsed.prefix,
        suffix=parsed.suffix,
        number_start=parsed.number_start,
        number_step=parsed.number_step,
        number_format=parsed.number_format,
        case_style=parsed.case,
        recursive=parsed.recursive,
    )

    changes = [item for item in plan if item.matched]

    if not changes:
        msg = "No files matched the renaming criteria or no changes required."
        print(msg)
        return 0

    print(f"=== Rename Preview ({len(changes)} files to rename) ===")
    for item in changes:
        print(f"  {item.source.name}  ==>  {item.target.name}")

    collisions = check_collisions(plan)
    if collisions:
        err_msg = "\nERROR: Collisions detected! Cannot proceed with rename:"
        print(err_msg, file=sys.stderr)
        for col in collisions:
            print(f"  - {col}", file=sys.stderr)
        return 1

    if parsed.dry_run or not parsed.apply:
        print("\n[DRY RUN] No files were renamed. Use --apply to execute.")
        return 0

    if not parsed.yes:
        c_msg = f"\nProceed with renaming {len(changes)} file(s)? [y/N]: "
        confirm = input(c_msg)
        if confirm.lower() != "y":
            print("Renaming cancelled.")
            return 0

    manifest_file = Path(parsed.manifest)
    results = execute_rename_plan(plan, manifest_path=manifest_file)
    print(f"\nSuccessfully renamed {len(results)} file(s).")
    print(f"Undo manifest saved to '{manifest_file}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
