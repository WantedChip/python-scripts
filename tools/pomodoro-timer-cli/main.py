"""Pomodoro Timer CLI tool.

Terminal Pomodoro timer with customizable work/break intervals, ASCII progress
bar, terminal notifications/beeps, and JSON session history persistence.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_HISTORY_FILE = Path.home() / ".pomodoro_history.json"


def format_progress_bar(
    elapsed_seconds: int, total_seconds: int, length: int = 30
) -> str:
    """Format ASCII progress bar for timer output."""
    if total_seconds <= 0:
        pct = 1.0
    else:
        pct = min(1.0, elapsed_seconds / total_seconds)

    filled = int(length * pct)
    bar_graph = "█" * filled + "░" * (length - filled)

    elapsed_m, elapsed_s = divmod(elapsed_seconds, 60)
    total_m, total_s = divmod(total_seconds, 60)

    time_str = f"{elapsed_m:02d}:{elapsed_s:02d} / {total_m:02d}:{total_s:02d}"
    return f"[{bar_graph}] {pct * 100:5.1f}% ({time_str})"


class SessionManager:
    """Manages reading and persisting Pomodoro session history."""

    def __init__(self, history_file: Path = DEFAULT_HISTORY_FILE):
        self.history_file = history_file

    def load_history(self) -> List[Dict[str, Any]]:
        """Load past session records from history JSON file."""
        if not self.history_file.exists():
            return []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                return []
        except (json.JSONDecodeError, OSError):
            return []

    def record_session(
        self, session_type: str, duration_minutes: float, completed: bool
    ) -> Dict[str, Any]:
        """Record a newly completed or interrupted session."""
        history = self.load_history()
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": session_type,
            "duration_minutes": duration_minutes,
            "completed": completed,
        }
        history.append(entry)

        # Ensure parent folder exists
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)

        return entry

    def get_stats(self) -> Dict[str, Any]:
        """Calculate aggregate session statistics."""
        history = self.load_history()
        total_work_min = 0.0
        total_break_min = 0.0
        completed_work_sessions = 0
        completed_break_sessions = 0

        for item in history:
            if item.get("completed"):
                if item.get("type") == "work":
                    completed_work_sessions += 1
                    total_work_min += float(item.get("duration_minutes", 0))
                else:
                    completed_break_sessions += 1
                    total_break_min += float(item.get("duration_minutes", 0))

        return {
            "total_sessions": float(len(history)),
            "completed_work_sessions": float(completed_work_sessions),
            "completed_break_sessions": float(completed_break_sessions),
            "total_work_minutes": total_work_min,
            "total_break_minutes": total_break_min,
        }


def run_timer(
    duration_seconds: int,
    label: str = "Work",
    tick_delay: float = 1.0,
    notify_beep: bool = True,
) -> bool:
    """Run timer loop with live ASCII progress bar updates.

    Returns True if session finished, False if interrupted by user (Ctrl+C).
    """
    mins = duration_seconds // 60
    print(f"\n--- Starting {label} Timer ({mins} min) ---")
    try:
        for elapsed in range(duration_seconds + 1):
            bar_str = format_progress_bar(elapsed, duration_seconds)
            sys.stdout.write(f"\r{label}: {bar_str}")
            sys.stdout.flush()
            if elapsed < duration_seconds:
                time.sleep(tick_delay)
        sys.stdout.write("\n")
        if notify_beep:
            sys.stdout.write("\a")  # Terminal bell notification
            sys.stdout.flush()
        print(f"🎉 {label} session completed!")
        return True
    except KeyboardInterrupt:
        sys.stdout.write("\n")
        print(f"\n⚠️ {label} session interrupted by user.")
        return False


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Terminal Pomodoro Timer CLI"
    parser = argparse.ArgumentParser(description=desc)
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to run")

    start_parser = subparsers.add_parser("start", help="Start Pomodoro cycle")
    start_parser.add_argument(
        "-w",
        "--work",
        type=float,
        default=25.0,
        help="Work interval (min)",
    )
    start_parser.add_argument(
        "-b",
        "--break",
        type=float,
        default=5.0,
        dest="break_time",
        help="Break interval (min)",
    )
    start_parser.add_argument(
        "-c", "--cycles", type=int, default=1, help="Number of work cycles"
    )
    start_parser.add_argument(
        "--history-file",
        type=Path,
        default=DEFAULT_HISTORY_FILE,
        help="History file path",
    )
    start_parser.add_argument(
        "--test-mode", action="store_true", help="Speed up timer for testing"
    )

    stats_parser = subparsers.add_parser("stats", help="View session history stats")
    stats_parser.add_argument(
        "--history-file",
        type=Path,
        default=DEFAULT_HISTORY_FILE,
        help="History file path",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entrypoint for Pomodoro Timer."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    if parsed.command == "stats" or parsed.command is None:
        hist_file = getattr(parsed, "history_file", DEFAULT_HISTORY_FILE)
        manager = SessionManager(hist_file)
        stats = manager.get_stats()
        tot = int(stats["total_sessions"])
        c_work = int(stats["completed_work_sessions"])
        c_brk = int(stats["completed_break_sessions"])
        w_min = stats["total_work_minutes"]
        b_min = stats["total_break_minutes"]

        print("\n=== Pomodoro Session Stats ===")
        print(f"Total Logged Sessions:       {tot}")
        print(f"Completed Work Sessions:     {c_work}")
        print(f"Completed Break Sessions:    {c_brk}")
        print(f"Total Work Time:             {w_min:.1f} minutes")
        print(f"Total Break Time:            {b_min:.1f} minutes")
        return 0

    if parsed.command == "start":
        manager = SessionManager(parsed.history_file)
        tick_delay = 0.01 if parsed.test_mode else 1.0

        for cycle in range(1, parsed.cycles + 1):
            print(f"\n=== Cycle {cycle} of {parsed.cycles} ===")

            # Work Session
            is_tm = parsed.test_mode
            w_sec = int(parsed.work * 60) if not is_tm else int(parsed.work)
            w_ok = run_timer(w_sec, label="Work", tick_delay=tick_delay)
            manager.record_session("work", parsed.work, w_ok)

            if not w_ok:
                print("Stopping Pomodoro routine.")
                break

            # Break Session (if not final cycle)
            if cycle < parsed.cycles:
                b_sec = (
                    int(parsed.break_time * 60) if not is_tm else int(parsed.break_time)
                )
                b_ok = run_timer(b_sec, label="Break", tick_delay=tick_delay)
                manager.record_session("break", parsed.break_time, b_ok)

                if not b_ok:
                    print("Stopping Pomodoro routine.")
                    break

    return 0


if __name__ == "__main__":
    sys.exit(main())
