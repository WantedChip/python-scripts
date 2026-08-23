#!/usr/bin/env python3
"""Scheduled Task Auditor.

Audits cron jobs, systemd timers, startup scripts, and Windows Task Scheduler
entries to verify executable paths and flag broken tasks.
"""

import argparse
import csv
import io
import os
import re
import shutil
import subprocess  # nosec B404
import sys
from typing import Dict, List, Tuple


def get_windows_tasks() -> List[Dict[str, str]]:
    """Query Windows Task Scheduler using schtasks CLI."""
    tasks: List[Dict[str, str]] = []
    if sys.platform != "win32":
        return tasks

    try:
        # Run schtasks query in verbose CSV format
        res = subprocess.run(
            ["schtasks", "/query", "/fo", "csv", "/v"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec
        if res.returncode != 0:
            return tasks

        # Parse CSV output
        f = io.StringIO(res.stdout)
        reader = csv.DictReader(f)
        for row in reader:
            task_name = row.get("TaskName", "")
            task_run = row.get("Task To Run", "")
            status = row.get("Status", "Unknown")
            trigger = row.get("Trigger Type", "")

            if task_name and task_run:
                tasks.append(
                    {
                        "name": task_name,
                        "command": task_run,
                        "source": "Task Scheduler",
                        "trigger": trigger,
                        "status": status,
                    }
                )
    except Exception:  # nosec B110 # pylint: disable=broad-exception-caught
        pass
    return tasks


def get_windows_startup_entries() -> List[Dict[str, str]]:
    """Scan Windows Startup directories for link/script targets."""
    entries: List[Dict[str, str]] = []
    if sys.platform != "win32":
        return entries

    startup_paths = []
    # User startup
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        startup_paths.append(
            os.path.join(
                user_profile,
                "AppData",
                "Roaming",
                "Microsoft",
                "Windows",
                "Start Menu",
                "Programs",
                "Startup",
            )
        )
    # System startup
    program_data = os.environ.get("ProgramData")
    if program_data:
        startup_paths.append(
            os.path.join(
                program_data,
                "Microsoft",
                "Windows",
                "Start Menu",
                "Programs",
                "Startup",
            )
        )

    for path in startup_paths:
        if os.path.exists(path):
            try:
                for item in os.listdir(path):
                    full_path = os.path.join(path, item)
                    entries.append(
                        {
                            "name": item,
                            "command": full_path,
                            "source": "Startup Folder",
                            "trigger": "On Login",
                            "status": "Active",
                        }
                    )
            except OSError:
                pass
    return entries


# pylint: disable=too-many-branches,too-many-nested-blocks
def get_unix_cron_entries() -> List[Dict[str, str]]:
    """Scan crontab files in Unix settings."""
    entries: List[Dict[str, str]] = []
    if sys.platform == "win32":
        return entries

    # Scan standard crontab files
    cron_files = ["/etc/crontab"]
    cron_dirs = [
        "/etc/cron.d",
        "/etc/cron.daily",
        "/etc/cron.hourly",
        "/etc/cron.weekly",
        "/etc/cron.monthly",
    ]

    for cdir in cron_dirs:
        if os.path.exists(cdir):
            try:
                for entry in os.listdir(cdir):
                    cron_files.append(os.path.join(cdir, entry))
            except OSError:
                pass

    for fp in cron_files:
        if os.path.exists(fp) and os.path.isfile(fp):
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    for idx, line in enumerate(f, 1):
                        line_strip = line.strip()
                        if not line_strip or line_strip.startswith("#"):
                            continue
                        entries.append(
                            {
                                "name": f"{os.path.basename(fp)}:line_{idx}",
                                "command": line_strip,
                                "source": "Cron Configuration",
                                "trigger": "Cron Schedule",
                                "status": "Active",
                            }
                        )
            except OSError:
                pass

    # Also parse current user crontab
    try:
        res = subprocess.run(
            ["crontab", "-l"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec
        if res.returncode == 0:
            for idx, line in enumerate(res.stdout.split("\n"), 1):
                line_strip = line.strip()
                if not line_strip or line_strip.startswith("#"):
                    continue
                entries.append(
                    {
                        "name": f"User Crontab:line_{idx}",
                        "command": line_strip,
                        "source": "User Crontab",
                        "trigger": "Cron Schedule",
                        "status": "Active",
                    }
                )
    except OSError:
        pass

    return entries


def get_unix_systemd_timers() -> List[Dict[str, str]]:
    """Scan systemd timer configuration entries."""
    entries: List[Dict[str, str]] = []
    if sys.platform == "win32":
        return entries

    timer_paths = ["/etc/systemd/system/", "/usr/lib/systemd/system/"]
    for path in timer_paths:
        if not os.path.exists(path):
            continue
        try:
            for f in os.listdir(path):
                if f.endswith(".timer"):
                    timer_file = os.path.join(path, f)
                    service_file = timer_file.replace(".timer", ".service")

                    # Read command from matching service if possible
                    cmd = "Unknown (matching service missing)"
                    if os.path.exists(service_file):
                        try:
                            with open(
                                service_file, "r", encoding="utf-8", errors="replace"
                            ) as sf:
                                for line in sf:
                                    if line.strip().startswith("ExecStart="):
                                        cmd = line.strip().split("=", 1)[1]
                                        break
                        except OSError:
                            pass

                    entries.append(
                        {
                            "name": f,
                            "command": cmd,
                            "source": "Systemd Timer",
                            "trigger": "Systemd Schedule",
                            "status": "Active",
                        }
                    )
        except OSError:
            pass
    return entries


def parse_executable(command: str) -> str:
    """Extract the first word executable name, stripping quotes/parameters."""
    cmd_strip = command.strip()
    if not cmd_strip:
        return ""

    # Handle quotes
    if cmd_strip.startswith('"'):
        match = re.match(r'^"([^"]+)"', cmd_strip)
        if match:
            return match.group(1)

    if cmd_strip.startswith("'"):
        match = re.match(r"^'([^']+)'", cmd_strip)
        if match:
            return match.group(1)

    # Split by spaces, take first item
    parts = cmd_strip.split()
    return parts[0] if parts else ""


def audit_command(command: str) -> Tuple[str, str]:
    """Check if the command executable exists or is reachable in PATH."""
    exec_path = parse_executable(command)
    if not exec_path:
        return "Unknown", "Empty command string"

    # If it has path indicators (absolute/relative)
    if "/" in exec_path or "\\" in exec_path:
        if os.path.exists(exec_path):
            return "OK", "Path verified"
        return "Critical", f"Executable path does not exist: '{exec_path}'"

    # Check standard PATH
    found_path = shutil.which(exec_path)
    if found_path:
        return "OK", f"Executable '{exec_path}' found on PATH ({found_path})"
    return "Warning", f"Executable '{exec_path}' not found on active PATH"


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description="Unified scheduled tasks and startup scripts auditor."
    )
    parser.parse_args()

    print("========================================================================")
    print("SCHEDULED TASK AUDITOR: CONSOLIDATED SECURITY REPORT")
    print("========================================================================")

    # Gather tasks
    tasks = []
    if sys.platform == "win32":
        print("Gathering Windows scheduled tasks and startup entries...")
        tasks.extend(get_windows_tasks())
        tasks.extend(get_windows_startup_entries())
    else:
        print("Gathering Unix cron, crontabs, and systemd timers...")
        tasks.extend(get_unix_cron_entries())
        tasks.extend(get_unix_systemd_timers())

    if not tasks:
        print(
            "\n[-] No scheduled tasks or startup entries retrieved from system "
            "profiles."
        )
        sys.exit(0)

    print(f"Retrieved {len(tasks)} tasks. Starting reachability diagnostics...")
    print("-" * 80)

    issues = []

    # Audit each task
    for t in tasks:
        level, reason = audit_command(t["command"])
        if level in ("Warning", "Critical"):
            issues.append(
                {
                    "level": level,
                    "name": t["name"],
                    "source": t["source"],
                    "trigger": t["trigger"],
                    "command": t["command"],
                    "reason": reason,
                }
            )

    if not issues:
        print(
            "\n[+] Success: All scheduled tasks have valid and reachable executable "
            "paths."
        )
        sys.exit(0)

    # Sort issues by severity (Critical first)
    issues.sort(key=lambda x: 1 if x["level"] == "Critical" else 2)

    print(f"\n[!] Flagged {len(issues)} broken or suspicious scheduled tasks:")
    print("=" * 80)

    for iss in issues:
        lvl_marker = f"[{iss['level']}]"
        print(f"{lvl_marker:<10} Task: {iss['name']}")
        print(f"           Source: {iss['source']} ({iss['trigger']})")
        print(f"           Command: {iss['command']}")
        print(f"           Issue:  {iss['reason']}")
        print("-" * 80)


if __name__ == "__main__":
    main()
