"""Cron Job Health Checker.

A utility to scan cron logs, identify failed runs, overlapping executions,
and missed schedules using native step-simulation parsing.
"""

import argparse
import datetime
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# pylint: disable=duplicate-code

logger = logging.getLogger("cron_health_checker")


@dataclass
class JobIssue:
    """Represents an identified issue with a scheduled cron job."""

    job_name: str
    issue_type: str  # 'FAILURE', 'OVERLAP', 'MISSED', 'STUCK'
    timestamp: str
    details: str


def setup_logging(verbose: bool) -> None:
    """Configure logger stream handler and level."""
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.setLevel(level)
    logger.addHandler(handler)
    logging.basicConfig(level=logging.WARNING, handlers=[handler])


def matches_field(val: int, field_pattern: str) -> bool:
    """Check if time value matches a single cron field pattern.

    Args:
        val: integer time value (e.g. minute, hour).
        field_pattern: cron pattern (e.g. '*', '*/5', '1-5', '1,2').

    Returns:
        True if matches, False otherwise.
    """
    # pylint: disable=too-many-return-statements
    if field_pattern == "*":
        return True
    if field_pattern.startswith("*/"):
        try:
            step = int(field_pattern[2:])
            return val % step == 0
        except ValueError:
            return False
    if "," in field_pattern:
        parts = field_pattern.split(",")
        return any(matches_field(val, p) for p in parts)
    if "-" in field_pattern:
        try:
            start, end = map(int, field_pattern.split("-"))
            return start <= val <= end
        except ValueError:
            return False
    try:
        return val == int(field_pattern)
    except ValueError:
        return False


def get_next_cron_time(dt: datetime.datetime, cron_expr: str) -> datetime.datetime:
    """Calculate next scheduled time from cron expression using step-simulation.

    Args:
        dt: current datetime anchor.
        cron_expr: standard 5-field cron expression.

    Returns:
        Next scheduled datetime execution.
    """
    fields = cron_expr.split()
    if len(fields) < 5:
        raise ValueError(f"Invalid cron expression: '{cron_expr}'")

    current = dt + datetime.timedelta(minutes=1)
    # Search cap of 10000 steps to avoid hung processes
    for _ in range(10000):
        # cron day of week is 0-6 (Sunday-Saturday).
        # python weekday() is 0-6 (Monday-Sunday).
        # convert python weekday to cron: Monday=1, ..., Saturday=6, Sunday=0
        cron_wday = (current.weekday() + 1) % 7
        if (
            matches_field(current.minute, fields[0])
            and matches_field(current.hour, fields[1])
            and matches_field(current.day, fields[2])
            and matches_field(current.month, fields[3])
            and matches_field(cron_wday, fields[4])
        ):
            return current
        current += datetime.timedelta(minutes=1)

    return current


def parse_log_line(line: str) -> Optional[Tuple[datetime.datetime, str, str, str]]:
    """Parse standard timestamped cron log entries.

    Supports formats:
    - '2026-07-11 12:00:00 - job_name - START'
    - '2026-07-11 12:02:15 - job_name - END - SUCCESS'
    - '2026-07-11 12:06:30 - job_name - END - ERROR - msg'

    Args:
        line: Raw log line content.

    Returns:
        Tuple of (datetime, job_name, action, status/details) or None.
    """
    cleaned = line.strip()
    # Regex matching: timestamp - job_name - action - status
    match = re.match(
        r"^(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})\s*-\s*"
        r"([a-zA-Z0-9_\-]+)\s*-\s*(START|END)"
        r"(?:\s*-\s*([a-zA-Z0-9_\-\s]+))?",
        cleaned,
    )

    if not match:
        return None

    try:
        dt = datetime.datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

    job_name = match.group(2)
    action = match.group(3)
    status = match.group(4).strip() if match.group(4) else ""

    return dt, job_name, action, status


def check_cron_health(
    log_lines: List[str], schedules: Dict[str, str], threshold_min: int
) -> List[JobIssue]:
    """Analyze logs to identify job failures, overlaps, stuck jobs, and missed runs.

    Args:
        log_lines: List of logged run entries.
        schedules: Dictionary mapping job name to expected cron expression.
        threshold_min: minute threshold to flag stuck/long runs.

    Returns:
        List of identified JobIssue entries.
    """
    # pylint: disable=too-many-locals, too-many-branches
    issues = []

    # Tracks active job starts: {job_name: start_time}
    active_runs: Dict[str, datetime.datetime] = {}
    # Tracks run history for missed schedules checks: {job_name: [datetimes]}
    run_history: Dict[str, List[datetime.datetime]] = {}

    for line_num, line in enumerate(log_lines, 1):
        parsed = parse_log_line(line)
        if not parsed:
            continue

        dt, job, action, status = parsed
        run_history.setdefault(job, []).append(dt)

        if action == "START":
            if job in active_runs:
                # Overlap detected!
                issues.append(
                    JobIssue(
                        job_name=job,
                        issue_type="OVERLAP",
                        timestamp=dt.strftime("%Y-%m-%d %H:%M:%S"),
                        details=(
                            f"Job started at {dt} before preceding run "
                            f"finished (started at {active_runs[job]})."
                        ),
                    )
                )
            active_runs[job] = dt

        elif action == "END":
            if job in active_runs:
                del active_runs[job]

            if "ERROR" in status or "FAIL" in status:
                issues.append(
                    JobIssue(
                        job_name=job,
                        issue_type="FAILURE",
                        timestamp=dt.strftime("%Y-%m-%d %H:%M:%S"),
                        details=(
                            f"Job execution completed with errors: "
                            f"'{status}' (Line {line_num})."
                        ),
                    )
                )

    # 1. Check for Stuck Jobs (still active after threshold)
    now = datetime.datetime.now()
    for job, start_time in active_runs.items():
        elapsed = (now - start_time).total_seconds() / 60.0
        if elapsed > threshold_min:
            issues.append(
                JobIssue(
                    job_name=job,
                    issue_type="STUCK",
                    timestamp=start_time.strftime("%Y-%m-%d %H:%M:%S"),
                    details=(
                        f"Job remains active after {elapsed:.1f} minutes "
                        f"(started at {start_time})."
                    ),
                )
            )

    # 2. Check for Missed Schedules
    for job, cron_expr in schedules.items():
        history = sorted(run_history.get(job, []))
        if len(history) < 2:
            continue

        for i in range(len(history) - 1):
            prev_time = history[i]
            next_actual = history[i + 1]

            # Calculate next expected run time
            try:
                expected_time = get_next_cron_time(prev_time, cron_expr)
            except ValueError as err:
                logger.error("Skip schedule check for %s: %s", job, err)
                break

            # If actual run was later than expected (with 1-min grace margin)
            if next_actual > expected_time + datetime.timedelta(minutes=1):
                issues.append(
                    JobIssue(
                        job_name=job,
                        issue_type="MISSED",
                        timestamp=expected_time.strftime("%Y-%m-%d %H:%M:%S"),
                        details=(
                            f"Expected execution at {expected_time} was missed. "
                            f"Next run did not execute until {next_actual}."
                        ),
                    )
                )

    return issues


def print_terminal_summary(issues: List[JobIssue]) -> None:
    """Print cron audit report in clean terminal layout."""
    sys.stdout.write("\n=== Cron Job Health Audit Report ===\n\n")
    if not issues:
        sys.stdout.write("  No health issues identified. All jobs running normally.\n")
        sys.stdout.write("\n=====================================\n")
        return

    header_fmt = "{:<15} {:<12} {:<20} {}\n"
    sys.stdout.write(
        header_fmt.format("Job Name", "Issue Type", "Timestamp", "Description")
    )
    sys.stdout.write("-" * 90 + "\n")

    for issue in sorted(issues, key=lambda x: (x.timestamp, x.job_name)):
        sys.stdout.write(
            header_fmt.format(
                issue.job_name,
                issue.issue_type,
                issue.timestamp,
                issue.details,
            )
        )
    sys.stdout.write("\n=====================================\n")


def main() -> None:
    """CLI execution entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Cron Job Health Checker — inspect cron execution logs "
            "for failures and overlaps."
        )
    )
    parser.add_argument(
        "-i", "--input", required=True, type=Path, help="Path to target cron log file."
    )
    parser.add_argument(
        "-s",
        "--schedules",
        type=Path,
        help=(
            "JSON file mapping job name to expected cron expression "
            '(e.g. \'{"job_a": "*/5 * * * *"}\').'
        ),
    )
    parser.add_argument(
        "-t",
        "--threshold",
        type=int,
        default=60,
        help="Stuck warning threshold duration in minutes (default: 60).",
    )

    parser.add_argument(
        "-o", "--output", type=Path, help="Output report JSON file path."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose debug logging."
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    if not args.input.exists():
        logger.error("Log file not found: %s", args.input.as_posix())
        sys.exit(1)

    # 1. Parse schedules
    schedules = {}
    if args.schedules:
        if args.schedules.exists():
            try:
                schedules = json.loads(args.schedules.read_text(encoding="utf-8"))
                logger.info("Loaded expected schedules: %d entries", len(schedules))
            except Exception as err:  # pylint: disable=broad-exception-caught
                logger.error("Failed to parse schedules JSON: %s", err)
                sys.exit(1)
        else:
            logger.error("Schedules file not found: %s", args.schedules.as_posix())
            sys.exit(1)

    # 2. Read logs
    try:
        lines = args.input.read_text(encoding="utf-8", errors="replace").split("\n")
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.error("Failed to read log file: %s", err)
        sys.exit(1)

    # 3. Analyze health issues
    issues = check_cron_health(lines, schedules, args.threshold)

    # 4. Save/print results
    if args.output:
        try:

            with open(args.output, "w", encoding="utf-8") as f:
                json.dump([asdict(issue) for issue in issues], f, indent=2)
            logger.info("Saved health audit JSON report to: %s", args.output.as_posix())
        except Exception as err:  # pylint: disable=broad-exception-caught
            logger.error("Failed to save JSON report: %s", err)
            sys.exit(1)
    else:
        print_terminal_summary(issues)


if __name__ == "__main__":
    main()
