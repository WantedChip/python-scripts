#!/usr/bin/env python3
"""Config Archaeologist.

Scans standard configuration folders (AppData, .config, etc.) to discover
settings left behind by uninstalled software and scores them by staleness.
"""

import argparse
import os
import sys
from datetime import datetime
from typing import Any, Dict, Set, Tuple


# pylint: disable=too-many-branches
def get_installed_programs_windows() -> Set[str]:
    """Compile a set of lowercase program names found in Windows directories."""
    programs = set()
    paths_to_scan = []

    # Standard program directories
    pf = os.environ.get("ProgramFiles")
    if pf:
        paths_to_scan.append(pf)
    pf86 = os.environ.get("ProgramFiles(x86)")
    if pf86:
        paths_to_scan.append(pf86)

    localapp = os.environ.get("LOCALAPPDATA")
    if localapp:
        paths_to_scan.append(os.path.join(localapp, "Programs"))

    for path in paths_to_scan:
        if os.path.exists(path):
            try:
                for entry in os.listdir(path):
                    if os.path.isdir(os.path.join(path, entry)):
                        programs.add(entry.lower())
            except OSError:
                pass

    # Also parse folders in PATH
    for path in os.environ.get("PATH", "").split(os.pathsep):
        if os.path.exists(path):
            try:
                # Add executable filenames without extension
                for f in os.listdir(path):
                    if f.lower().endswith((".exe", ".bat", ".cmd")):
                        name, _ = os.path.splitext(f)
                        programs.add(name.lower())
            except OSError:
                pass

    return programs


def get_installed_programs_unix() -> Set[str]:
    """Compile Unix bin command names from PATH."""
    programs = set()

    # Standard bin dirs
    bin_paths = ["/usr/bin", "/bin", "/usr/sbin", "/sbin", "/usr/local/bin"]
    # Append PATH directories
    bin_paths.extend(os.environ.get("PATH", "").split(os.pathsep))

    for path in bin_paths:
        if os.path.exists(path):
            try:
                for entry in os.listdir(path):
                    programs.add(entry.lower())
            except OSError:
                pass
    return programs


def get_config_roots() -> Dict[str, str]:
    """Retrieve standard settings configuration roots for this OS."""
    roots = {}
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            roots["AppData Roaming"] = appdata
        localappdata = os.environ.get("LOCALAPPDATA")
        if localappdata:
            roots["AppData Local"] = localappdata
    else:
        home = os.path.expanduser("~")
        roots["User Config"] = os.path.join(home, ".config")
        roots["User Local Share"] = os.path.join(home, ".local", "share")

    return roots


def get_folder_metrics(path: str) -> Tuple[int, datetime]:
    """Calculate directory size and its newest file modification time."""
    total_size = 0
    newest_mtime = datetime.min

    try:
        # Check folder itself first
        stat_info = os.stat(path)
        newest_mtime = datetime.fromtimestamp(stat_info.st_mtime)

        for root, _, files in os.walk(path):
            for f in files:
                f_path = os.path.join(root, f)
                try:
                    f_stat = os.stat(f_path)
                    total_size += f_stat.st_size
                    mtime = datetime.fromtimestamp(f_stat.st_mtime)
                    newest_mtime = max(newest_mtime, mtime)
                except OSError:
                    pass
    except OSError:
        pass

    return total_size, newest_mtime


# pylint: disable=too-many-locals,too-many-branches,too-many-statements
def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description="Find old configuration files left behind by uninstalled software."
    )
    parser.add_argument(
        "-t",
        "--threshold",
        type=int,
        default=180,
        help=(
            "Age threshold in days. Folders older than this are prioritized for "
            "staleness (default: 180)."
        ),
    )
    parser.add_argument(
        "-c",
        "--confidence",
        type=int,
        default=50,
        help=(
            "Minimum confidence percentage threshold to display a stale candidate "
            "(default: 50)."
        ),
    )

    args = parser.parse_args()

    # Step 1: Query installed programs
    if sys.platform == "win32":
        installed = get_installed_programs_windows()
    else:
        installed = get_installed_programs_unix()

    # Step 2: Query settings roots
    roots = get_config_roots()
    if not roots:
        print(
            "Error: Could not locate configuration directories for this system.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("========================================================================")
    print("CONFIG ARCHAEOLOGIST: STALE CONFIGURATIONS DETECTOR")
    print("========================================================================")
    print(
        f"Scanning settings folders against {len(installed):,} active software "
        "signatures..."
    )

    candidates: list[dict[str, Any]] = []
    now = datetime.now()

    for root_name, root_path in roots.items():
        if not os.path.exists(root_path):
            continue

        print(f"Scanning {root_name}: {root_path}")
        try:
            entries = os.listdir(root_path)
        except OSError as e:
            print(f"  Warning: Cannot read {root_path}: {e}")
            continue

        for entry in entries:
            full_path = os.path.join(root_path, entry)
            if not os.path.isdir(full_path):
                continue

            # Skip hidden folders/standard system roots
            if entry.startswith(".") or entry.lower() in (
                "microsoft",
                "system32",
                "temp",
                "programs",
            ):
                continue

            # Calculate metrics
            size, newest_mtime = get_folder_metrics(full_path)
            age_days = (now - newest_mtime).days

            # Score staleness (max 100)
            score = 0
            reasons = []

            # Heuristics 1: Is matching executable/app installed?
            clean_entry = entry.lower().replace("-", "").replace("_", "")

            # Match directly or check close matching
            match_found = False
            for inst in installed:
                if inst == clean_entry or inst in clean_entry or clean_entry in inst:
                    match_found = True
                    break

            if not match_found:
                score += 60
                reasons.append(
                    "App signature not found in installation/bin directories"
                )

            # Heuristics 2: Date age scoring
            if newest_mtime == datetime.min:
                score += 20
                reasons.append("Unknown last modified timestamp (min value)")
            elif age_days > 365:
                score += 30
                reasons.append(f"Last updated {age_days:,} days ago (>1 year)")
            elif age_days > args.threshold:
                score += 15
                reasons.append(
                    f"Last updated {age_days:,} days ago (>{args.threshold} days)"
                )

            # Heuristics 3: Size heuristics
            if size == 0:
                score += 10
                reasons.append("Directory is empty (0 bytes content)")

            # Final limit
            score = min(score, 100)

            if score >= args.confidence:
                candidates.append(
                    {
                        "root": root_name,
                        "folder_name": entry,
                        "path": full_path,
                        "size_mb": size / (1024.0 * 1024.0),
                        "last_modified": newest_mtime,
                        "confidence": score,
                        "reasons": reasons,
                    }
                )

    # Print results
    if not candidates:
        print(
            "\n[+] No stale configuration candidates found above confidence threshold."
        )
        sys.exit(0)

    # Sort candidates by confidence (descending)
    candidates.sort(key=lambda x: int(x["confidence"]), reverse=True)

    print(f"\nFound {len(candidates)} stale candidate folders:")
    print("=" * 80)

    for idx, cand in enumerate(candidates, 1):
        last_mod = cand["last_modified"]
        modified_str = (
            last_mod.strftime("%Y-%m-%d")
            if hasattr(last_mod, "strftime") and last_mod != datetime.min
            else "Never"
        )
        print(f"{idx}. Folder: {cand['folder_name']} (Source: {cand['root']})")
        print(f"   Path:       {cand['path']}")
        print(f"   Confidence: {cand['confidence']}% Stale")
        print(f"   Size:       {cand['size_mb']:.2f} MB")
        print(f"   Last Active: {modified_str}")
        print("   Evidence Log:")
        reasons_list: list[str] = cand["reasons"]
        for reason in reasons_list:
            print(f"     - {reason}")
        print("-" * 80)


if __name__ == "__main__":
    main()
