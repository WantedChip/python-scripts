#!/usr/bin/env python3
"""Cleanup Simulator.

Scans local and system directories for cache, temp, and build directories to
calculate reclaimable space before running any cleanup commands.
"""

import argparse
import fnmatch
import os
import sys
from typing import Any, Dict, List, Tuple

# Target rule definition
CLEANUP_TARGETS: Dict[str, Dict[str, Any]] = {
    "python_cache": {
        "description": (
            "Python Cache directories (__pycache__, .pytest_cache, "
            ".mypy_cache, .coverage)"
        ),
        "patterns": ["__pycache__", ".pytest_cache", ".mypy_cache", ".coverage"],
        "is_dir": [True, True, True, False],
    },
    "build_artifacts": {
        "description": "Python build outputs (build, dist, *.egg-info)",
        "patterns": ["build", "dist", "*.egg-info"],
        "is_dir": [True, True, True],
    },
    "node_modules": {
        "description": "Node package modules (node_modules)",
        "patterns": ["node_modules"],
        "is_dir": [True],
    },
}


def get_system_targets() -> Dict[str, str]:
    """Retrieve standard system temp and package cache directories."""
    paths: Dict[str, str] = {}

    # OS Temp
    if sys.platform == "win32":
        temp = os.environ.get("TEMP")
        if temp:
            paths["system_temp"] = temp

        # Pip Cache
        localappdata = os.environ.get("LOCALAPPDATA")
        if localappdata:
            paths["pip_cache"] = os.path.join(localappdata, "pip", "Cache")

        # Npm Cache
        appdata = os.environ.get("APPDATA")
        if appdata:
            paths["npm_cache"] = os.path.join(appdata, "npm-cache")
    else:
        paths["system_temp"] = "/tmp"  # nosec B108
        home = os.path.expanduser("~")
        paths["pip_cache"] = os.path.join(home, ".cache", "pip")
        paths["npm_cache"] = os.path.join(home, ".npm")

    return paths


# pylint: disable=too-many-locals,too-many-branches,too-many-statements,too-many-nested-blocks  # noqa: E501
def scan_directory(
    target_dir: str, custom_globs: List[str]
) -> Dict[str, Dict[str, Any]]:
    """Scan the target directory recursively, grouping cleanable files by category."""
    results: Dict[str, Dict[str, Any]] = {
        cat: {"count": 0, "size": 0, "files": []} for cat in CLEANUP_TARGETS
    }

    if custom_globs:
        results["custom"] = {"count": 0, "size": 0, "files": []}

    target_dir = os.path.abspath(target_dir)

    for root, dirs, files in os.walk(target_dir):
        # 1. Check directories
        # Iterate backwards to allow safe modification in-place to skip
        # scanning inside deleted folders
        for idx in range(len(dirs) - 1, -1, -1):
            dname = dirs[idx]
            matched_cat = None

            for cat, rule in CLEANUP_TARGETS.items():
                patterns: List[str] = rule["patterns"]
                is_dir_flags: List[bool] = rule["is_dir"]
                for pat, is_dir_flag in zip(patterns, is_dir_flags):
                    if is_dir_flag and fnmatch.fnmatch(dname, pat):
                        matched_cat = cat
                        break
                if matched_cat:
                    break

            if matched_cat:
                # Calculate size of matched directory and delete from walk
                # to prevent deeper scanning
                full_dpath = os.path.join(root, dname)
                # Count files & size inside this directory
                d_count = 0
                d_size = 0
                for d_root, _, d_files in os.walk(full_dpath):
                    for df in d_files:
                        df_path = os.path.join(d_root, df)
                        try:
                            d_size += os.path.getsize(df_path)
                            d_count += 1
                        except OSError:
                            pass

                results[matched_cat]["count"] += d_count
                results[matched_cat]["size"] += d_size
                results[matched_cat]["files"].append((full_dpath, d_size, True))

                # Delete from walk search
                del dirs[idx]

        # 2. Check files
        for f in files:
            full_fpath = os.path.join(root, f)
            matched_cat = None

            # Check standard file rules (e.g. .coverage files)
            for cat, rule in CLEANUP_TARGETS.items():
                patterns = rule["patterns"]
                is_dir_flags = rule["is_dir"]
                for pat, is_dir_flag in zip(patterns, is_dir_flags):
                    if not is_dir_flag and fnmatch.fnmatch(f, pat):
                        matched_cat = cat
                        break
                if matched_cat:
                    break

            if matched_cat:
                try:
                    f_size = os.path.getsize(full_fpath)
                    results[matched_cat]["count"] += 1
                    results[matched_cat]["size"] += f_size
                    results[matched_cat]["files"].append((full_fpath, f_size, False))
                except OSError:
                    pass
            elif custom_globs:
                # Check custom glob pattern match
                for glob_pat in custom_globs:
                    if fnmatch.fnmatch(f, glob_pat):
                        try:
                            f_size = os.path.getsize(full_fpath)
                            results["custom"]["count"] += 1
                            results["custom"]["size"] += f_size
                            results["custom"]["files"].append(
                                (full_fpath, f_size, False)
                            )
                        except OSError:
                            pass
                        break

    return results


# pylint: disable=too-many-locals
def scan_system_caches(paths: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
    """Scan system temporary and package manager caches."""
    results: Dict[str, Dict[str, Any]] = {}
    for name, path in paths.items():
        cat_data: Dict[str, Any] = {"count": 0, "size": 0, "files": []}
        results[name] = cat_data
        if not os.path.exists(path):
            continue

        for root, _, files in os.walk(path):
            for f in files:
                f_path = os.path.join(root, f)
                try:
                    f_size = os.path.getsize(f_path)
                    cat_data["count"] = cat_data["count"] + 1
                    cat_data["size"] = cat_data["size"] + f_size
                    files_list: List[Tuple[str, int, bool]] = cat_data["files"]
                    files_list.append((f_path, f_size, False))
                except OSError:
                    pass
    return results


def print_simulation_report(results: Dict[str, Dict[str, Any]], limit: int) -> None:
    """Print the final cleanable space reports."""
    print("========================================================================")
    print("CLEANUP SIMULATION REPORT (READ-ONLY PREVIEW)")
    print("========================================================================")

    total_files = 0
    total_size = 0

    all_categories = sorted(results.keys())
    for cat in all_categories:
        metrics = results[cat]
        count = metrics["count"]
        size_mb = metrics["size"] / (1024.0 * 1024.0)

        total_files += count
        total_size += metrics["size"]

        description: str = cat
        if cat in CLEANUP_TARGETS:
            description = str(CLEANUP_TARGETS[cat]["description"])
        elif cat == "custom":
            description = "Custom glob pattern matches"
        elif cat == "system_temp":
            description = "System Temporary Directories"
        elif cat == "pip_cache":
            description = "Pip Package Manager Cache"
        elif cat == "npm_cache":
            description = "Npm Package Manager Cache"

        print(f"\nTarget: {description} ({cat})")
        print(f"  Estimated cleanable items: {count:,}")
        print(f"  Estimated reclaimable space: {size_mb:.2f} MB")

        # Print top largest files in this category
        if metrics["files"]:
            print("  Top cleanable paths:")
            sorted_files = sorted(metrics["files"], key=lambda x: x[1], reverse=True)
            for path, f_size, is_dir_flag in sorted_files[:limit]:
                sz_str = f"{f_size / (1024.0 * 1024.0):.2f} MB"
                dir_marker = "/" if is_dir_flag else ""
                print(f"    - {path}{dir_marker} ({sz_str})")

    print("\n" + "=" * 80)
    print("TOTAL CLEANUP SIMULATION SUMMARY:")
    print(f"  Total items reclaimable:  {total_files:,}")
    gb_str = f"{total_size / (1024.0 * 1024.0 * 1024.0):.2f} GB"
    mb_str = f"{total_size / (1024.0 * 1024.0):.2f} MB"
    print(f"  Total space reclaimable:  {gb_str} ({mb_str})")
    print("=" * 80)


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Simulate cleanup operations by listing what would be deleted and "
            "space recovered."
        )
    )

    parser.add_argument(
        "target_dir",
        nargs="?",
        default=".",
        help=(
            "Target folder to scan recursively for project build/cache items "
            "(default: current directory)."
        ),
    )
    parser.add_argument(
        "-s",
        "--system",
        action="store_true",
        help=(
            "Include system temporary folders and package manager caches "
            "(pip, npm) in simulation."
        ),
    )
    parser.add_argument(
        "-g",
        "--glob",
        help="Comma-separated custom file glob patterns to scan (e.g. *.log,*.tmp).",
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=int,
        default=5,
        help=(
            "Limit number of largest file path details listed per category "
            "(default: 5)."
        ),
    )

    args = parser.parse_args()

    # Custom globs
    custom_globs = (
        [g.strip() for g in args.glob.split(",") if g.strip()] if args.glob else []
    )

    # 1. Scan target project directory
    results = scan_directory(args.target_dir, custom_globs)

    # 2. Optionally scan system caches
    if args.system:
        sys_paths = get_system_targets()
        sys_results = scan_system_caches(sys_paths)
        results.update(sys_results)

    # 3. Print report
    print_simulation_report(results, args.limit)


if __name__ == "__main__":
    main()
