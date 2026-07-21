#!/usr/bin/env python3
"""Failure Pack.

Executes a command and, on failure, gathers system diagnostics, stdout, stderr,
sanitized environment names, recent log files, and packaging metadata into a
recoverable ZIP diagnostic bundle.
"""

import argparse
import json
import os
import platform
import subprocess  # nosec B404
import sys
import time
import zipfile
from datetime import datetime
from typing import Any, Dict, List


def get_system_diagnostics() -> Dict[str, Any]:
    """Compile non-sensitive details about the active OS and environment context."""
    env_keys = sorted(list(os.environ.keys()))

    packages = []
    try:
        res = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--format=json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec
        if res.returncode == 0:
            packages = json.loads(res.stdout)
    except (OSError, ValueError, json.JSONDecodeError):
        pass

    return {
        "timestamp": datetime.now().isoformat(),
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "architecture": platform.architecture()[0],
        "python_version": sys.version,
        "environment_variable_keys": env_keys,
        "installed_packages": packages,
    }


def find_related_logs_and_configs(cwd: str) -> List[str]:
    """Locate non-sensitive config and log files in the current workspace."""
    discovered = []
    config_extensions = (".json", ".yaml", ".yml", ".ini", ".conf", ".toml", ".txt")
    exclude_names = {".env", "package-lock.json", "poetry.lock"}

    for root, dirs, files in os.walk(cwd):
        dirs[:] = [
            d
            for d in dirs
            if d not in (".git", "venv", ".venv", "node_modules", "build", "dist")
        ]
        for f in files:
            fpath = os.path.join(root, f)
            try:
                if os.path.getsize(fpath) > 200 * 1024:
                    continue
            except OSError:
                continue

            ext = os.path.splitext(f)[1].lower()
            if ext == ".log":
                discovered.append(fpath)
            elif ext in config_extensions and f not in exclude_names:
                if f in (
                    "requirements.txt",
                    "setup.py",
                    "pyproject.toml",
                    "package.json",
                    "docker-compose.yml",
                ):
                    discovered.append(fpath)
    return discovered


# pylint: disable=too-many-locals,too-many-statements
def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description="Execute a command and bundle diagnostics on exit failure."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Generate bundle even if the target command passes (exit code 0).",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to run and bundle (prefix with -- e.g. -- python app.py).",
    )

    args = parser.parse_args()

    cmd_args = args.command
    if cmd_args and cmd_args[0] == "--":
        cmd_args = cmd_args[1:]

    if not cmd_args:
        print("Error: No command provided to execute. Example:", file=sys.stderr)
        print("  python failure_pack.py -- python app.py", file=sys.stderr)
        sys.exit(1)

    full_cmd = " ".join(cmd_args)
    print("========================================================================")
    print("FAILURE PACK: INCIDENT DIAGNOSTIC BUNDLER")
    print("========================================================================")
    print(f"Executing: {full_cmd}")
    print("-" * 80)

    start_time = time.time()
    res = subprocess.run(
        full_cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )  # nosec B602
    duration = time.time() - start_time

    print(f"Command exited with code: {res.returncode}")
    print(f"Duration:                  {duration:.2f} seconds")

    if res.returncode == 0 and not args.force:
        print("\n[+] Command executed cleanly. Skip diagnostics collection.")
        if res.stdout:
            print("\nStdout:")
            print(res.stdout)
        sys.exit(0)

    print("\n[!] Command failed (or --force set). Gathering diagnostic materials...")

    sys_diag = get_system_diagnostics()
    sys_diag["command_executed"] = full_cmd
    sys_diag["exit_code"] = res.returncode
    sys_diag["duration_seconds"] = duration

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bundle_name = f"failure_bundle_{timestamp}.zip"

    cwd = os.getcwd()
    related_files = find_related_logs_and_configs(cwd)

    try:
        with zipfile.ZipFile(bundle_name, "w", zipfile.ZIP_DEFLATED) as zipf:
            zipf.writestr("diagnostics_report.json", json.dumps(sys_diag, indent=4))
            zipf.writestr("stdout.log", res.stdout)
            zipf.writestr("stderr.log", res.stderr)

            for f in related_files:
                rel = os.path.relpath(f, cwd)
                if rel == bundle_name:
                    continue
                try:
                    zipf.write(f, os.path.join("workspace", rel))
                except OSError:
                    pass

        print(f"\n[+] Success: Diagnostic bundle packed to {bundle_name}")
        msg = (
            f"    Contents: report metadata, stdout/stderr logs, and "
            f"{len(related_files)} config/log files."
        )
        print(msg)
        print(
            "========================================================================"
        )
    except (OSError, ValueError) as e:
        print(
            f"[-] Error: Failed to create diagnostic ZIP bundle: {e}", file=sys.stderr
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
