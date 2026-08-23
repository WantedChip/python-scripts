#!/usr/bin/env python3
"""Context Switch.

Saves complete workspace development state (git branch, patch of changes,
active ports, recent notes, and TODOs) to allow seamless restore during tasks.
"""

import argparse
import json
import os
import subprocess  # nosec B404
import sys
from datetime import datetime
from typing import List, Optional

# Optional psutil
try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def get_current_branch(cwd: str) -> str:
    """Get active git branch name."""
    try:
        res = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec
        return res.stdout.strip() or "HEAD detached"
    except Exception:  # pylint: disable=broad-exception-caught
        return "Unknown"


def get_listening_ports() -> List[int]:
    """Retrieve listening ports owned by user-level development servers."""
    ports: List[int] = []
    if not HAS_PSUTIL:
        return ports
    try:
        for conn in psutil.net_connections(kind="tcp"):
            if conn.status == "LISTEN" and conn.laddr:
                if 3000 <= conn.laddr.port <= 9999 or conn.laddr.port in (
                    80,
                    443,
                    8080,
                    8443,
                ):
                    ports.append(conn.laddr.port)
    except (OSError, ValueError, AttributeError):
        pass
    return list(set(ports))


def run_save(name: str, storage_dir: str, notes: Optional[str]) -> None:
    """Create a new context save configuration file and git patch file."""
    cwd = os.getcwd()

    is_git = os.path.exists(os.path.join(cwd, ".git"))
    branch = get_current_branch(cwd) if is_git else "N/A"

    patch_path = os.path.join(storage_dir, f"{name}.patch")
    has_patch = False

    if is_git:
        try:
            status_res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )  # nosec
            if status_res.stdout.strip():
                with open(patch_path, "w", encoding="utf-8") as pf:
                    subprocess.run(
                        ["git", "diff", "HEAD"],
                        cwd=cwd,
                        stdout=pf,
                        stderr=subprocess.PIPE,
                        check=False,
                    )  # nosec
                has_patch = True
                print(f"Created workspace diff patch: {name}.patch")
        except (OSError, ValueError) as e:
            print(f"Warning: Failed to create git patch: {e}", file=sys.stderr)

    ports = get_listening_ports()

    meta = {
        "name": name,
        "timestamp": datetime.now().isoformat(),
        "directory": cwd,
        "branch": branch,
        "has_patch": has_patch,
        "ports": ports,
        "notes": notes or "",
    }

    meta_path = os.path.join(storage_dir, f"{name}.json")
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=4)
        print(f"Successfully saved development context '{name}' to {meta_path}")
    except OSError as e:
        print(f"Error saving context metadata: {e}", file=sys.stderr)


def run_restore(name: str, storage_dir: str) -> None:
    """Load context configuration, restore git branch/patch, and audit dev ports."""
    meta_path = os.path.join(storage_dir, f"{name}.json")
    if not os.path.exists(meta_path):
        print(f"Error: Context profile '{name}' not found.", file=sys.stderr)
        return

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error loading context: {e}", file=sys.stderr)
        return

    cwd = os.getcwd()
    print("========================================================================")
    print(f"RESTORE DEVELOPMENT CONTEXT: '{name}'")
    print("========================================================================")
    print(f"Saved At:       {meta['timestamp']}")
    print(f"Saved Directory: {meta['directory']}")

    if meta["directory"] != cwd:
        print(
            "Warning: Active directory differs. Restoring state in current folder.",
            file=sys.stderr,
        )

    # 1. Restore Branch
    is_git = os.path.exists(os.path.join(cwd, ".git"))
    if is_git and meta["branch"] != "N/A":
        current_branch = get_current_branch(cwd)
        if current_branch != meta["branch"]:
            print(f"Checking out saved branch: {meta['branch']}...")
            subprocess.run(
                ["git", "checkout", meta["branch"]], cwd=cwd, check=False
            )  # nosec

    # 2. Apply patch
    if meta["has_patch"]:
        patch_path = os.path.join(storage_dir, f"{name}.patch")
        if os.path.exists(patch_path):
            print("Applying saved changes patch file...")
            subprocess.run(["git", "apply", patch_path], cwd=cwd, check=False)  # nosec

    # 3. Check dev servers ports status
    active_ports = get_listening_ports()
    missing_ports = [p for p in meta["ports"] if p not in active_ports]
    if missing_ports:
        print(
            "\n[!] ALERT: Dev servers previously listening on ports "
            f"{missing_ports} are not active."
        )
        print("    Please launch project dev servers to resume full execution flow.")

    # 4. Display notes
    if meta["notes"]:
        print("\nSaved Task Notes / TODOs:")
        print(meta["notes"])
    print("=" * 80)


def run_list(storage_dir: str) -> None:
    """List all saved development contexts."""
    files = [f for f in os.listdir(storage_dir) if f.endswith(".json")]
    if not files:
        print("No saved development contexts found.")
        return

    print("========================================================================")
    print("SAVED DEVELOPMENT CONTEXTS")
    print("========================================================================")
    print(f"{'NAME':<12} | {'SAVED AT':<19} | {'BRANCH':<15} | {'DIRECTORY'}")
    print("-" * 80)
    for f in files:
        fpath = os.path.join(storage_dir, f)
        try:
            with open(fpath, "r", encoding="utf-8") as fh:
                meta = json.load(fh)
            clean_time = meta["timestamp"][:19].replace("T", " ")
            disp_dir = meta["directory"]
            if len(disp_dir) > 30:
                disp_dir = "..." + disp_dir[-27:]
            print(
                f"{meta['name']:<12} | {clean_time:<19} | {meta['branch']:<15} | "
                f"{disp_dir}"
            )
        except (json.JSONDecodeError, OSError):
            pass
    print("=" * 80)


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Save or restore development contexts (branch, patches, ports, " "notes)."
        )
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute.")

    # Save
    save_parser = subparsers.add_parser(
        "save", help="Save the current development context."
    )
    save_parser.add_argument("name", help="Name label for this context profile.")
    save_parser.add_argument(
        "-n", "--notes", help="Text notes or pending TODO tasks to save with state."
    )

    # Restore
    restore_parser = subparsers.add_parser(
        "restore", help="Restore a saved development context."
    )
    restore_parser.add_argument(
        "name", help="Name label of the context profile to load."
    )

    # List
    subparsers.add_parser("list", help="List all saved contexts.")

    args = parser.parse_args()

    home = os.path.expanduser("~")
    storage_dir = os.path.join(home, ".context_switches")
    os.makedirs(storage_dir, exist_ok=True)

    if args.command == "save":
        run_save(args.name, storage_dir, args.notes)
    elif args.command == "restore":
        run_restore(args.name, storage_dir)
    elif args.command == "list":
        run_list(storage_dir)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
