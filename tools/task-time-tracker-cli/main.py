"""Task Time Tracker CLI.

Tracks time spent on tasks with start/stop/switch commands,
project tagging, aggregated daily/weekly reporting, and CSV exports.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods
# pylint: disable=redefined-builtin,broad-exception-caught


STORAGE_FILE = "time_tracker.json"


def format_duration(seconds: float) -> str:
    """Formats duration in seconds into HH:MM:SS format."""
    total_sec = int(round(seconds))
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    secs = total_sec % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


class TimeSession:
    """Model representing a task timing session."""

    def __init__(
        self,
        id: int,
        task: str,
        project: str = "General",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        duration_seconds: float = 0.0,
    ) -> None:
        self.id = id
        self.task = task
        self.project = project
        self.start_time = start_time or datetime.datetime.now().isoformat()
        self.end_time = end_time
        self.duration_seconds = duration_seconds

    def is_active(self) -> bool:
        """Returns True if the session is currently active (no end_time)."""
        return self.end_time is None

    def get_duration(self) -> float:
        """Get session duration."""
        return self.calculate_duration()

    def calculate_duration(self) -> float:
        """Calculates duration in seconds."""
        if self.end_time:
            return self.duration_seconds
        start_dt = datetime.datetime.fromisoformat(self.start_time)
        return (datetime.datetime.now() - start_dt).total_seconds()

    def stop(self) -> None:
        """Stops the active session and records duration."""
        if self.is_active():
            now = datetime.datetime.now()
            self.end_time = now.isoformat()
            start_dt = datetime.datetime.fromisoformat(self.start_time)
            self.duration_seconds = (now - start_dt).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Converts session object to dictionary."""
        return {
            "id": self.id,
            "task": self.task,
            "project": self.project,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TimeSession:
        """Creates session object from dictionary."""
        return cls(
            id=data["id"],
            task=data["task"],
            project=data.get("project", "General"),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            duration_seconds=data.get("duration_seconds", 0.0),
        )


class TimeTrackerManager:
    """Manages time sessions, active state, reporting, and CSV output."""

    def __init__(self, filepath: str = STORAGE_FILE) -> None:
        self.filepath = filepath
        self.sessions: List[TimeSession] = self.load()

    def load(self) -> List[TimeSession]:
        """Loads sessions from storage file."""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return [TimeSession.from_dict(s) for s in data]
            except Exception:
                return []
        return []

    def save(self) -> None:
        """Saves session records to storage file."""
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump([s.to_dict() for s in self.sessions], f, indent=2)

    def _generate_id(self) -> int:
        if not self.sessions:
            return 1
        return max(s.id for s in self.sessions) + 1

    def get_active_session(self) -> Optional[TimeSession]:
        """Get active session alias."""
        return self.get_active()

    def get_active(self) -> Optional[TimeSession]:
        """Returns currently active session if any."""
        for s in self.sessions:
            if s.is_active():
                return s
        return None

    def start_task(self, task: str, project: str = "General") -> TimeSession:
        """Starts a new task timer. Stops any existing active task."""
        self.stop_task()
        s_id = self._generate_id()
        session = TimeSession(id=s_id, task=task, project=project)
        self.sessions.append(session)
        self.save()
        return session

    def stop_task(self) -> Optional[TimeSession]:
        """Stops current active task timer if running."""
        active = self.get_active()
        if active:
            active.stop()
            self.save()
            return active
        return None

    def switch_task(
        self, new_task: str, new_project: str = "General"
    ) -> Tuple[Optional[TimeSession], TimeSession]:
        """Switches from current task to a new task."""
        stopped = self.stop_task()
        started = self.start_task(new_task, new_project)
        return stopped, started

    def get_report(
        self, period: str = "all", project_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generates aggregated summary report for specified time period.

        Supported periods: 'daily', 'weekly', 'all'.
        """
        now = datetime.datetime.now()
        filtered_sessions: List[TimeSession] = []

        for s in self.sessions:
            if project_filter and s.project.lower() != project_filter.lower():
                continue

            s_start = datetime.datetime.fromisoformat(s.start_time)
            if period == "daily":
                if s_start.date() == now.date():
                    filtered_sessions.append(s)
            elif period == "weekly":
                s_week = now.date() - datetime.timedelta(days=now.weekday())
                if s_start.date() >= s_week:
                    filtered_sessions.append(s)
            else:
                filtered_sessions.append(s)

        project_totals: Dict[str, float] = {}
        task_totals: Dict[str, float] = {}
        total_seconds = 0.0

        for s in filtered_sessions:
            dur = s.calculate_duration()
            total_seconds += dur

            p_val = project_totals.get(s.project, 0.0)
            project_totals[s.project] = p_val + dur

            task_key = f"{s.project}: {s.task}"
            t_val = task_totals.get(task_key, 0.0)
            task_totals[task_key] = t_val + dur

        return {
            "period": period,
            "total_seconds": total_seconds,
            "project_totals": project_totals,
            "task_totals": task_totals,
            "session_count": len(filtered_sessions),
        }

    def export_csv(self, output_filepath: str) -> None:
        """Exports all time sessions to a CSV file."""
        headers = [
            "ID",
            "Task",
            "Project",
            "Start Time",
            "End Time",
            "Duration (Seconds)",
            "Duration (Formatted)",
        ]
        with open(output_filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for s in self.sessions:
                dur = s.calculate_duration()
                writer.writerow(
                    [
                        s.id,
                        s.task,
                        s.project,
                        s.start_time,
                        s.end_time or "ACTIVE",
                        round(dur, 2),
                        format_duration(dur),
                    ]
                )


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description="Task Time Tracker CLI")
    subparsers = parser.add_subparsers(dest="command", help="Subcommands")

    start_parser = subparsers.add_parser("start", help="Start a new task timer")
    start_parser.add_argument("task", help="Task description")
    start_parser.add_argument("--project", default="General", help="Project name")

    subparsers.add_parser("stop", help="Stop current active task timer")

    switch_parser = subparsers.add_parser("switch", help="Switch to a new task")
    switch_parser.add_argument("task", help="New task description")
    switch_parser.add_argument("--project", default="General", help="New project name")

    subparsers.add_parser("status", help="Show active task status")

    report_parser = subparsers.add_parser("report", help="Generate summary time report")
    report_parser.add_argument(
        "--period",
        choices=["daily", "weekly", "all"],
        default="daily",
        help="Time period",
    )
    report_parser.add_argument("--project", help="Filter by project name")

    export_parser = subparsers.add_parser("export", help="Export logs to CSV")
    export_parser.add_argument("--output", required=True, help="Output CSV file path")

    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI Entry point."""
    parser = build_parser()
    parsed = parser.parse_args(args)
    mgr = TimeTrackerManager()

    if parsed.command == "start":
        s = mgr.start_task(parsed.task, parsed.project)
        print(f"Started task [{s.id}] '{s.task}' under project '{s.project}'")

    elif parsed.command == "stop":
        stopped = mgr.stop_task()
        if stopped:
            dur_str = format_duration(stopped.duration_seconds)
            print(f"Stopped task '{stopped.task}'. Duration: {dur_str}")
        else:
            print("No active task running.")

    elif parsed.command == "switch":
        stopped, started = mgr.switch_task(parsed.task, parsed.project)
        if stopped:
            dur_str = format_duration(stopped.duration_seconds)
            print(f"Stopped task '{stopped.task}' ({dur_str}).")
        proj = started.project
        print(
            f"Switched to task [{started.id}] '{started.task}' under"
            f" project '{proj}'"
        )

    elif parsed.command == "status":
        active = mgr.get_active()
        if active:
            dur = active.calculate_duration()
            print("\n=== ACTIVE TASK ===")
            print(f" Task   : {active.task}")
            print(f" Project: {active.project}")
            print(f" Started: {active.start_time}")
            print(f" Elapsed: {format_duration(dur)}")
        else:
            print("No task currently active.")

    elif parsed.command == "report":
        rpt = mgr.get_report(period=parsed.period, project_filter=parsed.project)
        print(f"\n=== SUMMARY REPORT ({rpt['period'].upper()}) ===")
        print(f"Total Time Tracked: {format_duration(rpt['total_seconds'])}")
        print(f"Total Sessions    : {rpt['session_count']}\n")

        print("--- Project Totals ---")
        for proj, secs in rpt["project_totals"].items():
            print(f"  {proj:<20}: {format_duration(secs)}")

        print("\n--- Task Breakdown ---")
        for task_name, secs in rpt["task_totals"].items():
            print(f"  {task_name:<30}: {format_duration(secs)}")

    elif parsed.command == "export":
        mgr.export_csv(parsed.output)
        print(f"Exported time logs to '{parsed.output}'")

    else:
        parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())
