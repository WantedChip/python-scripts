#!/usr/bin/env python3
"""Process Family Tree.

Traces and displays the process lineage tree (ancestors, siblings, children) of
a target process, including CMD, CWD, ports, and connection details.
"""

import argparse
import os
import sys
from typing import List

# Import psutil
try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def format_process_info(proc: "psutil.Process") -> str:
    """Format single process details into an informative string."""
    try:
        pid = proc.pid
        name = proc.name()

        try:
            user = proc.username()
        except (OSError, psutil.Error):
            user = "Unknown"

        try:
            cmd = " ".join(proc.cmdline())
            if len(cmd) > 60:
                cmd = cmd[:57] + "..."
        except (OSError, psutil.Error):
            cmd = "N/A"

        try:
            cwd = proc.cwd()
        except (OSError, psutil.Error):
            cwd = "N/A"

        ports = []
        try:
            conns = proc.connections(kind="inet")
            for c in conns:
                if c.status == "LISTEN" and c.laddr:
                    ports.append(f":{c.laddr.port}")
        except (OSError, psutil.Error):
            pass
        ports_str = f" [Listening {','.join(ports)}]" if ports else ""

        res_line1 = f"{name} (PID: {pid}, Owner: {user}) [CWD: {cwd}]{ports_str}"
        return f"{res_line1}\n  └─ Cmd: {cmd}"
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return f"Process (PID: {proc.pid}) [Access Denied / Ended]"


def print_tree(
    ancestors: List["psutil.Process"],
    target: "psutil.Process",
    children: List["psutil.Process"],
) -> None:
    """Render the ASCII tree representing parents and child relationships."""
    print("========================================================================")
    print("PROCESS FAMILY TREE DIAGNOSTICS")
    print("========================================================================")

    print("Ancestry Lineage (Grandparents -> Parent):")
    indent = ""
    for idx, ancestor in enumerate(reversed(ancestors)):
        prefix = "  " * idx
        marker = "└─ " if idx > 0 else ""
        print(f"{prefix}{marker}{format_process_info(ancestor)}")
        indent = "  " * (idx + 1)

    target_prefix = indent + "└─ [TARGET] "
    print(f"\n{target_prefix}{format_process_info(target)}")

    if children:
        print("\nChild Processes:")
        child_indent = indent + "    "
        for child in children:
            print(f"{child_indent}└─ {format_process_info(child)}")
    else:
        print("\nChild Processes: None active")
    print("=" * 80)


def find_process_by_name(name: str) -> List["psutil.Process"]:
    """Search active processes matching case-insensitive name."""
    matches = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if name.lower() in proc.info["name"].lower():
                matches.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return matches


# pylint: disable=too-many-branches,too-many-statements
def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Show process ancestry, working directory, and children of "
            "background processes."
        )
    )
    parser.add_argument(
        "target",
        nargs="?",
        help=(
            "Target PID number or process name query string (defaults to "
            "current Python process)."
        ),
    )

    args = parser.parse_args()

    if not HAS_PSUTIL:
        print(
            "Error: Required library 'psutil' is not installed.\n"
            "Please install it: pip install psutil",
            file=sys.stderr,
        )
        sys.exit(1)

    target_proc = None

    if not args.target:
        target_pid = os.getpid()
        try:
            target_proc = psutil.Process(target_pid)
        except psutil.NoSuchProcess:
            pass
    elif args.target.isdigit():
        target_pid = int(args.target)
        try:
            target_proc = psutil.Process(target_pid)
        except psutil.NoSuchProcess:
            print(
                f"Error: No active process found with PID: {target_pid}",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        procs = find_process_by_name(args.target)
        if not procs:
            print(
                f"Error: No processes matched name query: '{args.target}'",
                file=sys.stderr,
            )
            sys.exit(1)
        if len(procs) == 1:
            target_proc = procs[0]
        else:
            print(f"Multiple processes matched '{args.target}':")
            for p in procs:
                print(f"  PID: {p.pid:<6} | Name: {p.name()}")
            print("\nPlease specify a unique PID from above.", file=sys.stderr)
            sys.exit(1)

    if not target_proc:
        print("Error: Could not resolve target process.", file=sys.stderr)
        sys.exit(1)

    ancestors = []
    curr = target_proc
    try:
        while True:
            parent = curr.parent()
            if not parent or parent.pid == curr.pid:
                break
            ancestors.append(parent)
            curr = parent
    except (OSError, psutil.Error):
        pass

    children = []
    try:
        children = target_proc.children(recursive=True)
    except (OSError, psutil.Error):
        pass

    print_tree(ancestors, target_proc, children)


if __name__ == "__main__":
    main()
