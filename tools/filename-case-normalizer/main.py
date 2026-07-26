"""Filename Case Normalizer CLI tool.

Bulk convert filenames to lowercase, uppercase, title case, or snake_case with
collision prevention, dry-run preview mode, and undo manifest support.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Optional, Set, Tuple


def to_snake_case(name: str) -> str:
    """Convert string to snake_case."""
    # Insert underscore before capital letters if preceded by lower/digit
    s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    # Replace non-alphanumeric chars with underscores
    s2 = re.sub(r"[^\w]+", "_", s1)
    # Remove leading/trailing underscores and multiple underscores
    s3 = re.sub(r"_+", "_", s2).strip("_")
    return s3.lower() if s3 else name.lower()


def convert_filename(
    filename: str, mode: str, keep_extension_case: bool = False
) -> str:
    """Convert a filename according to the requested casing mode.

    Preserves file extensions appropriately.
    """
    path = Path(filename)
    stem = path.stem
    ext = path.suffix

    if not keep_extension_case:
        ext = ext.lower()

    if mode == "lowercase":
        new_stem = stem.lower()
    elif mode == "uppercase":
        new_stem = stem.upper()
    elif mode == "title":
        new_stem = stem.title()
    elif mode == "snake":
        new_stem = to_snake_case(stem)
    else:
        raise ValueError(f"Unsupported casing mode: {mode}")

    return f"{new_stem}{ext}"


def resolve_collision(
    target_path: Path,
    existing_targets: Set[str],
    strategy: str = "append_number",
) -> Optional[Path]:
    """Resolve potential file collision using the specified strategy.

    Strategies:
      - append_number: append _1, _2, etc. before extension
      - skip: return None to indicate skipping
      - overwrite: return target_path as is
    """
    target_resolved = str(target_path.resolve())
    if target_resolved not in existing_targets and not target_path.exists():
        return target_path

    if strategy == "overwrite":
        return target_path

    if strategy == "skip":
        return None

    if strategy == "append_number":
        parent = target_path.parent
        stem = target_path.stem
        ext = target_path.suffix
        counter = 1
        while True:
            candidate = parent / f"{stem}_{counter}{ext}"
            cand_res = str(candidate.resolve())
            if cand_res not in existing_targets and not candidate.exists():
                return candidate
            counter += 1

    raise ValueError(f"Unknown collision strategy: {strategy}")


def process_directory(
    directory: Path,
    mode: str,
    recursive: bool = False,
    collision_strategy: str = "append_number",
    dry_run: bool = False,
    manifest_path: Optional[Path] = None,
) -> List[Tuple[Path, Path]]:
    """Process filenames in directory and apply case normalization.

    Returns list of (original_path, new_path) tuples.
    """
    if not directory.exists() or not directory.is_dir():
        raise FileNotFoundError(f"Directory non-existent: {directory}")

    pattern = "**/*" if recursive else "*"
    files = [p for p in directory.glob(pattern) if p.is_file()]

    renames: List[Tuple[Path, Path]] = []
    seen_targets: Set[str] = set()

    for file_path in files:
        new_name = convert_filename(file_path.name, mode)
        proposed_target = file_path.parent / new_name

        if proposed_target == file_path:
            continue  # No change required

        resolved_target = resolve_collision(
            proposed_target, seen_targets, collision_strategy
        )
        if resolved_target is None:
            continue  # Skipped due to collision strategy

        seen_targets.add(str(resolved_target.resolve()))
        renames.append((file_path, resolved_target))

    if not dry_run:
        manifest_data = []
        for src, dst in renames:
            src.rename(dst)
            item = {
                "original": str(src.resolve()),
                "renamed": str(dst.resolve()),
            }
            manifest_data.append(item)

        if manifest_path:
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest_data, f, indent=2)

    return renames


def undo_renames(manifest_path: Path) -> int:
    """Undo renames using a previously saved JSON manifest.

    Returns count of restored files.
    """
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    restored = 0
    for item in data:
        orig = Path(item["original"])
        renamed = Path(item["renamed"])
        if renamed.exists():
            renamed.rename(orig)
            restored += 1
    return restored


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Filename Case Normalizer CLI tool"
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("directory", nargs="?", type=Path, help="Directory to process")
    parser.add_argument(
        "--mode",
        choices=["lowercase", "uppercase", "title", "snake"],
        default="lowercase",
        help="Casing mode (default: lowercase)",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Process recursively",
    )
    parser.add_argument(
        "--collision",
        choices=["append_number", "skip", "overwrite"],
        default="append_number",
        help="Collision handling strategy (default: append_number)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview renames without executing",
    )
    parser.add_argument("--manifest", type=Path, help="Save undo manifest to JSON file")
    parser.add_argument("--undo", type=Path, help="Undo renames using manifest file")
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entrypoint for filename case normalizer."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    if parsed.undo:
        count = undo_renames(parsed.undo)
        print(f"Successfully undone {count} renames.")
        return 0

    if not parsed.directory:
        parser.error("directory argument is required unless --undo is specified.")
        return 2

    renames = process_directory(
        directory=parsed.directory,
        mode=parsed.mode,
        recursive=parsed.recursive,
        collision_strategy=parsed.collision,
        dry_run=parsed.dry_run,
        manifest_path=parsed.manifest,
    )

    prefix = "[DRY-RUN] Would rename: " if parsed.dry_run else "Renamed: "
    for src, dst in renames:
        print(f"{prefix}{src.name} -> {dst.name}")

    print(f"\nTotal files processed: {len(renames)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
