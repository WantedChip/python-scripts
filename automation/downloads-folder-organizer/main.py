#!/usr/bin/env python3
"""
Downloads Folder Organizer CLI

Features:
- Sort files into categorized subfolders (Documents, Images, etc.)
- Extension and MIME type based categorization
- Custom category rules via JSON configuration
- Optional date-based subfolders (e.g. Documents/2026-07)
- Intelligent collision resolution (e.g. filename_1.ext)
- Dry-run preview mode
- Undo manifest logging and rollback support
"""

import argparse
import datetime
import json
import mimetypes
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_RULES: Dict[str, List[str]] = {
    "Documents": [
        ".pdf",
        ".docx",
        ".doc",
        ".txt",
        ".rtf",
        ".xlsx",
        ".pptx",
        ".csv",
        ".epub",
        ".ods",
        ".odt",
    ],
    "Images": [
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".webp",
        ".bmp",
        ".ico",
        ".tiff",
        ".heic",
    ],
    "Archives": [".zip", ".tar", ".gz", ".7z", ".rar", ".bz2", ".xz"],
    "Audio": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"],
    "Video": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"],
    "Code": [
        ".py",
        ".js",
        ".html",
        ".css",
        ".json",
        ".ts",
        ".cpp",
        ".h",
        ".java",
        ".sh",
        ".ps1",
        ".rb",
        ".go",
        ".rs",
        ".sql",
    ],
}


@dataclass
class MovePlanItem:
    """Represents a proposed file organization move action."""

    source: Path
    target: Path
    category: str


def load_category_rules(
    custom_config_path: Optional[Path] = None,
) -> Dict[str, List[str]]:
    """
    Loads categorization rules. Custom rules from JSON take precedence.
    """
    rules: Dict[str, List[str]] = {}

    if custom_config_path:
        if not custom_config_path.exists():
            raise FileNotFoundError(
                f"Custom rules file '{custom_config_path}' not found."
            )
        with open(custom_config_path, "r", encoding="utf-8") as f:
            custom_rules = json.load(f)

        for cat, exts in custom_rules.items():
            cleaned_exts = [e if e.startswith(".") else f".{e}" for e in exts]
            rules[cat] = [e.lower() for e in cleaned_exts]

    claimed = {ext for exts_list in rules.values() for ext in exts_list}
    for cat, exts in DEFAULT_RULES.items():
        if cat not in rules:
            rules[cat] = [e for e in exts if e.lower() not in claimed]

    return rules


def categorize_file(filepath: Path, rules: Dict[str, List[str]]) -> str:
    """
    Determines category based on file extension, falling back to MIME type.
    """
    ext = filepath.suffix.lower()

    # 1. Match by extension
    for category, exts in rules.items():
        if ext in exts:
            return category

    # 2. Match by MIME type
    mime_type, _ = mimetypes.guess_type(filepath)
    if mime_type:
        main_type = mime_type.split("/")[0]
        mime_mapping = {
            "image": "Images",
            "audio": "Audio",
            "video": "Video",
            "text": "Documents",
        }
        if main_type in mime_mapping and mime_mapping[main_type] in rules:
            return mime_mapping[main_type]

    return "Others"


def resolve_collision(target_path: Path) -> Path:
    """
    Generates a non-colliding path by appending _1, _2, etc., before the extension.
    """
    if not target_path.exists():
        return target_path

    parent = target_path.parent
    stem = target_path.stem
    ext = target_path.suffix

    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{ext}"
        if not candidate.exists():
            return candidate
        counter += 1


def build_organize_plan(
    directory: Path,
    rules: Dict[str, List[str]],
    by_date: bool = False,
    date_format: str = "%Y-%m",
    exclude_folders: Optional[List[str]] = None,
) -> List[MovePlanItem]:
    """
    Builds plan for organizing files in the directory.
    """
    if not directory.exists() or not directory.is_dir():
        raise ValueError(
            f"Directory '{directory}' does not exist or is not a directory."
        )

    ignored_names = set(rules.keys())
    ignored_names.add("Others")
    if exclude_folders:
        ignored_names.update(exclude_folders)

    plan: List[MovePlanItem] = []

    for item in directory.iterdir():
        # Only process top-level files
        if not item.is_file():
            continue

        category = categorize_file(item, rules)
        target_dir = directory / category

        if by_date:
            try:
                mtime = item.stat().st_mtime
                date_dt = datetime.datetime.fromtimestamp(mtime)
                date_str = date_dt.strftime(date_format)
                target_dir = target_dir / date_str
            except OSError:
                pass

        raw_target_path = target_dir / item.name
        final_target_path = resolve_collision(raw_target_path)

        plan.append(
            MovePlanItem(source=item, target=final_target_path, category=category)
        )

    return plan


def execute_organize_plan(
    plan: List[MovePlanItem], manifest_path: Optional[Path] = None
) -> List[Tuple[str, str]]:
    """
    Executes the file moves and logs an undo manifest JSON.
    """
    executed: List[Tuple[str, str]] = []

    for item in plan:
        try:
            item.target.parent.mkdir(parents=True, exist_ok=True)
            item.source.rename(item.target)
            executed.append((str(item.source.resolve()), str(item.target.resolve())))
        except Exception as err:  # pylint: disable=broad-exception-caught
            print(f"Failed to move '{item.source.name}': {err}", file=sys.stderr)

    if manifest_path and executed:
        manifest_data = {
            "moves": [{"source": src, "target": tgt} for src, tgt in executed]
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

    return executed


def rollback_organize(manifest_path: Path) -> List[Tuple[str, str]]:
    """
    Rolls back file movement using the undo manifest JSON.
    """
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest file '{manifest_path}' not found.")

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    moves = data.get("moves", [])
    restored: List[Tuple[str, str]] = []

    for item in reversed(moves):
        src_path = Path(item["source"])
        tgt_path = Path(item["target"])

        if tgt_path.exists():
            src_path.parent.mkdir(parents=True, exist_ok=True)
            tgt_path.rename(src_path)
            restored.append((str(tgt_path), str(src_path)))

    return restored


def main() -> None:
    """CLI entrypoint for Downloads Folder Organizer."""
    # pylint: disable=too-many-locals
    parser = argparse.ArgumentParser(
        description=(
            "Organize Downloads folder into categorized subfolders with date "
            "sorting and undo support."
        )
    )
    parser.add_argument(
        "--dir",
        "-d",
        default=".",
        help="Directory to organize (default: current directory)",
    )
    parser.add_argument(
        "--config", "-c", help="Path to custom category rules JSON file"
    )
    parser.add_argument(
        "--by-date",
        action="store_true",
        help="Organize into subfolders by file modification date",
    )
    parser.add_argument(
        "--date-format",
        default="%Y-%m",
        help="Format string for date subfolders (default: %%Y-%%m)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview file moves without executing",
    )
    parser.add_argument(
        "--apply", action="store_true", help="Execute the file organization moves"
    )
    parser.add_argument(
        "--yes", "-y", action="store_true", help="Skip confirmation prompt"
    )
    parser.add_argument(
        "--manifest",
        default="organize_undo.json",
        help="Path for undo JSON log manifest",
    )
    parser.add_argument(
        "--undo",
        action="store_true",
        help="Rollback previous organization using manifest",
    )

    args = parser.parse_args()

    if args.undo:
        manifest_file = Path(args.manifest)
        try:
            rolled_back = rollback_organize(manifest_file)
            count = len(rolled_back)
            print(f"Undo completed! Restored {count} file(s) to original locations.")
            for tgt, src in rolled_back:
                print(f"  Restored: {Path(tgt).name} -> {Path(src).name}")
        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"Error during undo: {e}", file=sys.stderr)
            sys.exit(1)
        return

    target_dir = Path(args.dir)
    config_file = Path(args.config) if args.config else None
    rules = load_category_rules(config_file)

    plan = build_organize_plan(
        directory=target_dir,
        rules=rules,
        by_date=args.by_date,
        date_format=args.date_format,
    )

    if not plan:
        print("No loose files found to organize.")
        return

    print(f"=== Organization Preview ({len(plan)} files to move) ===")
    for item in plan:
        rel_target = item.target.relative_to(target_dir)
        print(f"  [{item.category}] {item.source.name} ==> {rel_target}")

    if args.dry_run or not args.apply:
        print("\n[DRY RUN] No files were moved. Use --apply to execute.")
        return

    if not args.yes:
        confirm = input(f"\nProceed with moving {len(plan)} file(s)? [y/N]: ")
        if confirm.lower() != "y":
            print("Operation cancelled.")
            return

    manifest_file = Path(args.manifest)
    executed = execute_organize_plan(plan, manifest_path=manifest_file)
    print(f"\nSuccessfully organized {len(executed)} file(s).")
    print(f"Undo log written to '{manifest_file}'.")


if __name__ == "__main__":
    main()
