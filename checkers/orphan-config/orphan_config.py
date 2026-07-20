#!/usr/bin/env python3
"""Orphan Config.

Identifies directories in standard application configuration locations (e.g. AppData)
that do not correlate with any installed software executable or package.
"""

import argparse
import os
import shutil
import sys
from typing import Any, Dict, List


def get_common_app_paths() -> List[str]:
    """Retrieve standard program installation locations based on OS platform."""
    paths = []
    if sys.platform == "win32":
        # Check Program Files
        for var in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData"):
            val = os.environ.get(var)
            if val:
                paths.append(val)
    elif sys.platform == "darwin":
        paths.append("/Applications")
        paths.append("/usr/local/bin")
    else:
        paths.append("/usr/bin")
        paths.append("/usr/local/bin")
        paths.append("/opt")
    return paths


def verify_active_binary(name: str, app_paths: List[str]) -> bool:
    """Verify if a program matching the folder name exists on PATH or install paths."""
    # 1. Check PATH lookup
    if shutil.which(name):
        return True

    # Check common suffix forms
    if sys.platform == "win32" and shutil.which(f"{name}.exe"):
        return True

    # 2. Check standard installation directories
    for parent in app_paths:
        if os.path.exists(parent):
            try:
                # Check for direct match inside folder names
                for item in os.listdir(parent):
                    if name.lower() in item.lower():
                        return True
            except OSError:
                pass
    return False


def get_dir_size(path: str) -> int:
    """Calculate absolute disk storage space used by a directory in bytes."""
    total = 0
    try:
        for root, _, files in os.walk(path):
            for f in files:
                fpath = os.path.join(root, f)
                try:
                    total += os.path.getsize(fpath)
                except OSError:
                    pass
    except OSError:
        pass
    return total


# pylint: disable=too-many-locals,too-many-branches,too-many-statements
def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Identify configuration folders left behind by uninstalled software."
        )
    )
    parser.parse_args()

    # Determine configuration search folders
    home = os.path.expanduser("~")
    search_dirs = []

    if sys.platform == "win32":
        roaming = os.environ.get("AppData")
        local = os.environ.get("LocalAppData")
        if roaming:
            search_dirs.append(roaming)
        if local:
            search_dirs.append(local)
    else:
        # Unix/macOS
        search_dirs.append(os.path.join(home, ".config"))
        if sys.platform == "darwin":
            search_dirs.append(os.path.join(home, "Library", "Application Support"))

    app_paths = get_common_app_paths()

    print("========================================================================")
    print("ORPHAN CONFIG: STALE SETTINGS DISCOVERER")
    print("========================================================================")
    print(f"Auditing config paths: {', '.join(search_dirs)}")
    print("Correlating folder profiles to active system executables...")
    print("-" * 80)

    orphan_candidates: List[Dict[str, Any]] = []

    for sdir in search_dirs:
        if not os.path.exists(sdir):
            continue

        try:
            items = os.listdir(sdir)
        except OSError:
            continue

        for item in items:
            full_path = os.path.join(sdir, item)
            if not os.path.isdir(full_path):
                continue

            # Skip hidden folders or generic profiles
            if item.startswith(".") or item.lower() in (
                "temp",
                "microsoft",
                "apple",
                "google",
                "python",
                "git",
            ):
                continue

            # Check if correlating binary exists
            if not verify_active_binary(item, app_paths):
                size_bytes = get_dir_size(full_path)
                size_mb = size_bytes / (1024 * 1024)
                orphan_candidates.append(
                    {"name": item, "path": full_path, "size_mb": size_mb}
                )

    if not orphan_candidates:
        print(
            "\n[+] Success: All configuration folders correlate with active "
            "system programs."
        )
        sys.exit(0)

    # Sort orphans by size (descending)
    orphan_candidates.sort(key=lambda x: float(x["size_mb"]), reverse=True)

    print(f"\nDiscovered {len(orphan_candidates)} likely orphan config folders:")
    print("=" * 80)
    print(f"{'FOLDER NAME':<20} | {'DISK SIZE':<11} | {'LOCATION'}")
    print("-" * 80)
    for c in orphan_candidates:
        disp_path = str(c["path"])
        if len(disp_path) > 42:
            disp_path = "..." + disp_path[-39:]
        name = str(c["name"])
        size_mb = float(c["size_mb"])
        print(f"{name[:20]:<20} | {size_mb:.1f} MB     | {disp_path}")
    print("=" * 80)
    print(
        "Verify if software has been uninstalled before manually deleting "
        "directories."
    )


if __name__ == "__main__":
    main()
