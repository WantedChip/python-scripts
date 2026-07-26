"""CLI Countdown Timer with progress display and presets.

Parses human-readable duration strings, displays animated progress bars,
and alerts completion via terminal bell.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from typing import Callable, Dict, List, Optional

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods


PRESET_TIMERS: Dict[str, int] = {
    "pomodoro": 1500,  # 25 minutes
    "short-break": 300,  # 5 minutes
    "long-break": 900,  # 15 minutes
    "tea": 180,  # 3 minutes
    "egg": 360,  # 6 minutes
}


def parse_duration(duration_str: str) -> int:
    """Parse human readable duration string into total seconds.

    Supports formats like '10m', '1h30s', '45s', '2h15m30s', or plain integers.

    Args:
        duration_str: Duration string.

    Returns:
        Duration in seconds.

    Raises:
        ValueError: If duration string format is invalid or non-positive.
    """
    duration_str = duration_str.strip().lower()
    if not duration_str:
        raise ValueError("Duration string cannot be empty.")

    if duration_str.isdigit():
        sec = int(duration_str)
        if sec <= 0:
            raise ValueError("Duration must be greater than zero.")
        return sec

    pattern = (
        r"^(?:(?P<hours>\d+)h)?"
        + r"(?:(?P<minutes>\d+)m)?"
        + r"(?:(?P<seconds>\d+)s)?$"
    )
    match = re.match(pattern, duration_str)
    if not match or not any(match.groups()):
        err_msg = (
            f"Invalid duration format: '{duration_str}'. Example formats: "
            "'10m', '1h30s', '45s'."
        )
        raise ValueError(err_msg)

    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)

    total_seconds = hours * 3600 + minutes * 60 + seconds
    if total_seconds <= 0:
        raise ValueError("Duration must be greater than zero.")
    return total_seconds


def format_time(seconds: int) -> str:
    """Format total seconds into HH:MM:SS or MM:SS format.

    Args:
        seconds: Time in seconds.

    Returns:
        Formatted time string.
    """
    hrs = seconds // 3600
    mins = (seconds % 3600) // 60
    secs = seconds % 60
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def render_progress_bar(remaining: int, total: int, width: int = 25) -> str:
    """Generate ASCII progress bar string.

    Args:
        remaining: Remaining seconds.
        total: Total duration seconds.
        width: Width of character progress bar.

    Returns:
        Formatted progress bar line.
    """
    elapsed = total - remaining
    fraction = elapsed / total if total > 0 else 1.0
    filled = int(round(fraction * width))
    bar_str = "█" * filled + "░" * (width - filled)
    percent = int(fraction * 100)
    return f"[{bar_str}] {percent:3d}% | {format_time(remaining)} remaining"


class CountdownTimer:
    """Countdown timer executor."""

    def __init__(
        self, duration_seconds: int, message: str = "Timer completed!"
    ) -> None:
        """Initialize timer with duration and completion message.

        Args:
            duration_seconds: Total duration in seconds.
            message: Completion message alert.
        """
        self.duration = duration_seconds
        self.message = message

    def run(
        self,
        non_interactive: bool = False,
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        """Execute the countdown loop.

        Args:
            non_interactive: If True, skips sleeping and terminal animation.
            callback: Optional callback invoked upon timer completion.
        """
        if non_interactive:
            msg = f"Non-interactive run for {self.duration}s completed."
            print(msg)
            if callback:
                callback()
            return

        print(f"Starting timer for {format_time(self.duration)}...")
        try:
            for remaining in range(self.duration, -1, -1):
                progress = render_progress_bar(remaining, self.duration)
                sys.stdout.write(f"\r{progress}")
                sys.stdout.flush()
                if remaining > 0:
                    time.sleep(1)
            sys.stdout.write("\n")
            print(f"\a🔔 {self.message}")
            if callback:
                callback()
        except KeyboardInterrupt:
            sys.stdout.write("\n")
            print("Timer cancelled by user.")


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description="CLI Countdown Timer")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-d", "--duration", help="Duration string (e.g. 10m, 1h30s, 45s)"
    )
    group.add_argument(
        "-p",
        "--preset",
        choices=list(PRESET_TIMERS.keys()),
        help="Choose a preset timer",
    )
    group.add_argument(
        "--list-presets",
        action="store_true",
        help="List all available timer presets",
    )

    parser.add_argument(
        "-m", "--message", default="Time is up!", help="Custom completion message"
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run without live countdown sleep loop",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entrypoint for Countdown Timer CLI."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    if parsed.list_presets:
        print("Available presets:")
        for name, sec in PRESET_TIMERS.items():
            print(f"  - {name}: {format_time(sec)} ({sec}s)")
        return 0

    duration = 0
    if parsed.preset:
        duration = PRESET_TIMERS[parsed.preset]
    elif parsed.duration:
        try:
            duration = parse_duration(parsed.duration)
        except ValueError as err:
            print(f"Error: {err}", file=sys.stderr)
            return 1
    else:
        print("Error: Specify either --duration or --preset", file=sys.stderr)
        parser.print_help()
        return 1

    timer = CountdownTimer(duration, message=parsed.message)
    timer.run(non_interactive=parsed.non_interactive)
    return 0


if __name__ == "__main__":
    sys.exit(main())
