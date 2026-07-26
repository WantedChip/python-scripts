"""Process Killer by Name / Pattern.

Enumerates running processes, matches them against regex patterns or PID lists,
and terminates matching processes safely with dry-run support and optional
confirmation.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods
# pylint: disable=unsupported-membership-test

import argparse
import re
import sys
from typing import Any, Dict, List, Optional

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def find_target_processes(
    pattern: Optional[str] = None,
    pids: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """Enumerate processes matching regex pattern or explicit PID list.

    Returns:
        List of dicts containing process metadata: pid, name, cmdline.
    """
    if not HAS_PSUTIL:
        err_msg = "psutil package is required for process enumeration."
        raise RuntimeError(err_msg)

    matched = []
    regex = re.compile(pattern, re.IGNORECASE) if pattern else None
    target_pids = set(pids) if pids else None

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            pinfo = proc.info
            pid = pinfo["pid"]
            name = pinfo["name"] or ""
            cmdline = " ".join(pinfo["cmdline"] or [])

            is_match = False
            if target_pids is not None and pid in target_pids:
                is_match = True
            elif regex:
                if regex.search(name) or regex.search(cmdline):
                    is_match = True

            if is_match:
                matched.append(
                    {
                        "pid": pid,
                        "name": name,
                        "cmdline": cmdline,
                        "proc_obj": proc,
                    }
                )
        except (
            psutil.NoSuchProcess,
            psutil.AccessDenied,
            psutil.ZombieProcess,
        ):
            continue

    return matched


def kill_processes(
    matched_procs: List[Dict[str, Any]],
    force: bool = False,
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    """Terminate or kill specified processes.

    Args:
        matched_procs: List of process dicts from find_target_processes.
        force: If True, uses SIGKILL (kill), else SIGTERM (terminate).
        dry_run: If True, simulates action without killing.

    Returns:
        List of dicts with execution status.
    """
    results = []
    for p in matched_procs:
        pid = p["pid"]
        name = p["name"]
        item: Dict[str, Any] = {
            "pid": pid,
            "name": name,
            "status": "SIMULATED" if dry_run else "PENDING",
            "error": None,
        }

        if dry_run:
            results.append(item)
            continue

        proc_obj: psutil.Process = p["proc_obj"]
        try:
            if force:
                proc_obj.kill()
                item["status"] = "KILLED (SIGKILL)"
            else:
                proc_obj.terminate()
                item["status"] = "TERMINATED (SIGTERM)"
        except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
            item["status"] = "FAILED"
            item["error"] = str(exc)

        results.append(item)

    return results


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Find and Terminate Processes by Name Pattern or PID"
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "-p",
        "--pattern",
        help="Regex pattern matching process name or cmdline (e.g. 'node.*')",
    )
    parser.add_argument(
        "--pids", type=int, nargs="+", help="List of explicit PIDs to kill"
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force kill (SIGKILL) instead of graceful termination (SIGTERM)",
    )
    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Simulate process termination without taking action",
    )
    parser.add_argument(
        "-y", "--yes", action="store_true", help="Skip confirmation prompt"
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entrypoint."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    if not parsed.pattern and not parsed.pids:
        parser.error("Either --pattern or --pids must be provided.")

    if not HAS_PSUTIL:
        err_out = (
            "Error: psutil is required. Please install via 'pip install" + " psutil'."
        )
        print(err_out, file=sys.stderr)
        return 1

    matched = find_target_processes(pattern=parsed.pattern, pids=parsed.pids)

    if not matched:
        print("No matching processes found.")
        return 0

    print(f"Found {len(matched)} matching process(es):")
    for p in matched:
        cmd_trunc = p["cmdline"][:50]
        print(f"  PID {p['pid']:<7} | Name: {p['name']:<20} | Cmd: {cmd_trunc}")

    if parsed.dry_run:
        print("\n[DRY RUN MODE] No processes were terminated.")
        return 0

    if not parsed.yes:
        prompt_str = (
            f"\nAre you sure you want to terminate these {len(matched)}"
            " process(es)? [y/N]: "
        )
        confirm = input(prompt_str)  # nosec B322
        if confirm.lower() not in ("y", "yes"):
            print("Operation cancelled by user.")
            return 0

    results = kill_processes(matched, force=parsed.force, dry_run=False)

    print("\nTermination Summary:")
    for r in results:
        err_msg = f" ({r['error']})" if r["error"] else ""
        r_name = r["name"]
        r_stat = r["status"]
        print(f"  PID {r['pid']:<7} | {r_name:<20} | Status: {r_stat}{err_msg}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
