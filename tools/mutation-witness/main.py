"""Mutation Witness.

Catch process and command details responsible for file modifications. Records
file mutation events including responsible process PID, process name, parent
process command tree, working directory, size delta, and unified diffs.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import difflib
import hashlib
import json
import os
import subprocess  # nosec B404
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class FileSnapshot:
    """Snapshot of a file's state."""

    file_path: str
    exists: bool
    size_bytes: int
    mtime: float
    sha256: str
    content: str


@dataclass
class ProcessInfo:
    """Information about process responsible for mutation."""

    pid: int
    parent_pid: int
    process_name: str
    command_line: str
    working_directory: str
    parent_tree: List[Dict[str, Any]]


@dataclass
class MutationEvent:
    """Record of a single file mutation event."""

    timestamp_utc: str
    target_file: str
    action: str  # CREATED, MODIFIED, DELETED
    bytes_changed: int
    diff: str
    process_info: Dict[str, Any]


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    if not file_path.exists() or not file_path.is_file():
        return ""
    hasher = hashlib.sha256()
    try:
        with file_path.open("rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (OSError, ValueError):
        return ""


def take_snapshot(file_path: Path) -> FileSnapshot:
    """Take snapshot of target file."""
    resolved = file_path.resolve()
    if not resolved.exists():
        return FileSnapshot(
            file_path=str(resolved),
            exists=False,
            size_bytes=0,
            mtime=0.0,
            sha256="",
            content="",
        )

    size = resolved.stat().st_size
    mtime = resolved.stat().st_mtime
    sha = compute_sha256(resolved)
    try:
        content = resolved.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        content = ""

    return FileSnapshot(
        file_path=str(resolved),
        exists=True,
        size_bytes=size,
        mtime=mtime,
        sha256=sha,
        content=content,
    )


def get_process_tree(pid: Optional[int] = None) -> ProcessInfo:
    """Collect process info and parent process hierarchy."""
    target_pid = pid or os.getpid()
    parent_pid = os.getppid() if hasattr(os, "getppid") else 0

    proc_name = sys.executable
    cmd_line = " ".join(sys.argv)
    cwd = os.getcwd()

    parent_tree: List[Dict[str, Any]] = []

    # Attempt psutil if available
    try:
        import psutil  # pylint: disable=import-outside-toplevel

        p = psutil.Process(target_pid)
        proc_name = p.name()
        cmd_line = " ".join(p.cmdline())
        cwd = p.cwd()

        curr = p.parent()
        while curr:
            parent_tree.append(
                {
                    "pid": curr.pid,
                    "name": curr.name(),
                    "cmdline": " ".join(curr.cmdline()),
                }
            )
            curr = curr.parent()
    except (ImportError, Exception):  # pylint: disable=broad-exception-caught
        # Fallback stdlib inspection
        p_entry = {
            "pid": parent_pid,
            "name": "parent_process",
            "cmdline": "unknown",
        }
        parent_tree.append(p_entry)

    return ProcessInfo(
        pid=target_pid,
        parent_pid=parent_pid,
        process_name=proc_name,
        command_line=cmd_line,
        working_directory=cwd,
        parent_tree=parent_tree,
    )


def compute_diff(before: FileSnapshot, after: FileSnapshot) -> Tuple[str, int, str]:
    """Compute mutation action, bytes delta, and unified diff string."""
    if not before.exists and after.exists:
        action = "CREATED"
        delta = after.size_bytes
        diff_lines = difflib.unified_diff(
            [],
            after.content.splitlines(),
            fromfile="/dev/null",
            tofile=f"b/{Path(after.file_path).name}",
            lineterm="",
        )
        diff = "\n".join(diff_lines)
    elif before.exists and not after.exists:
        action = "DELETED"
        delta = -before.size_bytes
        diff = f"--- File deleted (was {before.size_bytes} bytes)"
    else:
        action = "MODIFIED"
        delta = after.size_bytes - before.size_bytes
        diff_lines = difflib.unified_diff(
            before.content.splitlines(),
            after.content.splitlines(),
            fromfile=f"a/{Path(before.file_path).name}",
            tofile=f"b/{Path(after.file_path).name}",
            lineterm="",
        )
        diff = "\n".join(diff_lines)

    return action, delta, diff


def wrap_command(
    file_path: Path,
    cmd_args: List[str],
    log_output: Optional[Path] = None,
) -> Optional[MutationEvent]:
    """Wrap command execution and witness file mutation."""
    before_snap = take_snapshot(file_path)

    cmd_str = " ".join(cmd_args)
    print(f"[Mutation Witness] Executing wrapped command: {cmd_str}")

    proc = subprocess.run(cmd_args, cwd=os.getcwd(), check=False)  # nosec B603

    after_snap = take_snapshot(file_path)

    has_same_sha = before_snap.sha256 == after_snap.sha256
    has_same_exists = before_snap.exists == after_snap.exists
    if has_same_sha and has_same_exists:
        print("[Mutation Witness] No file mutation detected.")
        return None

    action, delta, diff = compute_diff(before_snap, after_snap)
    target_pid = proc.pid if hasattr(proc, "pid") else os.getpid()
    proc_info = get_process_tree(target_pid)

    event = MutationEvent(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        target_file=str(file_path.resolve()),
        action=action,
        bytes_changed=delta,
        diff=diff,
        process_info=asdict(proc_info),
    )

    if log_output:
        save_mutation_event(event, log_output)

    return event


def watch_file(
    file_path: Path,
    interval_sec: float = 0.5,
    max_duration: Optional[float] = None,
    log_output: Optional[Path] = None,
) -> List[MutationEvent]:
    """Watch target file for mutations over time."""
    events: List[MutationEvent] = []
    current_snap = take_snapshot(file_path)

    msg = f"[Mutation Witness] Watching '{file_path}' ({interval_sec}s)..."
    print(msg)
    start_time = time.time()

    try:
        while True:
            if max_duration and (time.time() - start_time) > max_duration:
                break
            time.sleep(interval_sec)
            new_snap = take_snapshot(file_path)
            changed_sha = current_snap.sha256 != new_snap.sha256
            changed_exists = current_snap.exists != new_snap.exists
            if changed_sha or changed_exists:
                action, delta, diff = compute_diff(current_snap, new_snap)
                proc_info = get_process_tree()

                event = MutationEvent(
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    target_file=str(file_path.resolve()),
                    action=action,
                    bytes_changed=delta,
                    diff=diff,
                    process_info=asdict(proc_info),
                )
                events.append(event)
                print(f"[Mutation Witness] Detected {action} on '{file_path}'!")
                if log_output:
                    save_mutation_event(event, log_output)
                current_snap = new_snap
    except KeyboardInterrupt:
        print("\n[Mutation Witness] Stopping watch loop.")

    return events


def save_mutation_event(event: MutationEvent, log_file: Path) -> None:
    """Append mutation event to JSON log file."""
    existing = []
    if log_file.exists():
        try:
            existing = json.loads(log_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = []
    existing.append(asdict(event))
    log_file.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def format_text_event(event: MutationEvent) -> str:
    """Format mutation event to readable text summary."""
    p_pid = event.process_info["pid"]
    p_name = event.process_info["process_name"]
    lines = [
        "=== File Mutation Event ===",
        f"Timestamp:   {event.timestamp_utc}",
        f"Target File: {event.target_file}",
        f"Action:      {event.action} ({event.bytes_changed:+d} bytes)",
        f"Responsible PID: {p_pid} ({p_name})",
        f"Command Line:    {event.process_info['command_line']}",
        f"Working Dir:     {event.process_info['working_directory']}",
        "Diff:",
    ]
    for d in event.diff.splitlines():
        lines.append(f"  {d}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Catch process & command details responsible for file modifications."
    parser = argparse.ArgumentParser(description=desc)
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # Subcommand: wrap
    w_help = "Wrap command execution to monitor target file mutation"
    wrap_parser = subparsers.add_parser("wrap", help=w_help)
    wrap_parser.add_argument("--file", "-f", required=True, help="Target file to watch")
    wrap_parser.add_argument("--log", "-l", help="Log output JSON file")
    wrap_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )
    wrap_parser.add_argument("cmd", nargs=argparse.REMAINDER, help="Command to execute")

    # Subcommand: watch
    watch_parser = subparsers.add_parser("watch", help="Watch target file for changes")
    watch_parser.add_argument(
        "--file", "-f", required=True, help="Target file to watch"
    )
    watch_parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="Polling interval in seconds",
    )
    watch_parser.add_argument(
        "--duration", type=float, help="Max duration to watch in seconds"
    )
    watch_parser.add_argument("--log", "-l", help="Log output JSON file")
    watch_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )

    # Subcommand: report
    report_parser = subparsers.add_parser("report", help="Report recorded mutation log")
    report_parser.add_argument("log_file", help="Log file path")
    report_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint for mutation-witness."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    if parsed.subcommand == "wrap":
        cmd_args = parsed.cmd
        if cmd_args and cmd_args[0] == "--":
            cmd_args = cmd_args[1:]
        if not cmd_args:
            print("Error: No command provided to wrap.", file=sys.stderr)
            return 1

        log_path = Path(parsed.log) if parsed.log else None
        event = wrap_command(Path(parsed.file), cmd_args, log_output=log_path)
        if event:
            if parsed.format == "json":
                print(json.dumps(asdict(event), indent=2))
            else:
                print(format_text_event(event))
        else:
            return 0

    elif parsed.subcommand == "watch":
        log_path = Path(parsed.log) if parsed.log else None
        events = watch_file(
            Path(parsed.file),
            interval_sec=parsed.interval,
            max_duration=parsed.duration,
            log_output=log_path,
        )
        if parsed.format == "json":
            print(json.dumps([asdict(e) for e in events], indent=2))
        else:
            for e in events:
                print(format_text_event(e))

    elif parsed.subcommand == "report":
        log_file = Path(parsed.log_file)
        if not log_file.exists():
            print(
                f"Error: Log file '{log_file}' does not exist.",
                file=sys.stderr,
            )
            return 1

        events_data = json.loads(log_file.read_text(encoding="utf-8"))
        if parsed.format == "json":
            print(json.dumps(events_data, indent=2))
        else:
            for data in events_data:
                # Convert back to MutationEvent for text formatting
                event = MutationEvent(**data)
                print(format_text_event(event))
                print("-" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
