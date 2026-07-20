#!/usr/bin/env python3
"""README Doctor.

Extracts installation and configuration command blocks from README.md, sets up
an isolated virtualenv sandbox, executes them, and reports stale instructions.
"""

import argparse
import os
import re
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from typing import Any, Dict, List


def extract_commands(readme_path: str) -> List[str]:
    """Parse README.md and extract shell commands from code blocks."""
    commands: List[str] = []
    if not os.path.exists(readme_path):
        return commands

    try:
        with open(readme_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return commands

    block_pattern = re.compile(
        r"```(bash|sh|shell|cmd|console)\n(.*?)\n```", re.DOTALL | re.IGNORECASE
    )
    matches = block_pattern.findall(content)

    for _, block in matches:
        lines = block.split("\n")
        for line in lines:
            line_strip = line.strip()
            if (
                not line_strip
                or line_strip.startswith("#")
                or line_strip.startswith("::")
            ):
                continue

            # Strip prompt characters
            if line_strip.startswith("$ "):
                line_strip = line_strip[2:]
            elif line_strip.startswith("> "):
                line_strip = line_strip[2:]

            commands.append(line_strip)

    return commands


# pylint: disable=too-many-branches,too-many-statements,too-many-locals
def create_venv_and_run(commands: List[str], sandbox_dir: str) -> List[Dict[str, Any]]:
    """Initialize a venv and run commands inside, modifying python/pip calls."""
    results: List[Dict[str, Any]] = []

    # 1. Create venv
    venv_dir = os.path.join(sandbox_dir, "venv")
    print(f"Creating isolated virtualenv in: {venv_dir}...")
    try:
        subprocess.run(  # nosec B603
            [sys.executable, "-m", "venv", venv_dir],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as e:
        print(f"Failed to create venv: {e}", file=sys.stderr)
        return results

    # Determine python/pip executable paths
    if sys.platform == "win32":
        venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
        venv_pip = os.path.join(venv_dir, "Scripts", "pip.exe")
    else:
        venv_python = os.path.join(venv_dir, "bin", "python")
        venv_pip = os.path.join(venv_dir, "bin", "pip")

    # Copy local project descriptors to sandbox
    curr_dir = os.getcwd()
    for item in os.listdir(curr_dir):
        if os.path.abspath(item) == os.path.abspath(sandbox_dir):
            continue
        if item in (".git", "node_modules", "venv", ".venv", "__pycache__"):
            continue

        src_path = os.path.join(curr_dir, item)
        dest_path = os.path.join(sandbox_dir, item)
        try:
            if os.path.isdir(src_path):
                shutil.copytree(src_path, dest_path)
            else:
                shutil.copy2(src_path, dest_path)
        except OSError:
            pass

    # 2. Run commands
    for idx, cmd in enumerate(commands, 1):
        # Translate commands to use venv executables
        isolated_cmd = cmd
        if cmd.startswith("pip "):
            isolated_cmd = cmd.replace("pip ", f'"{venv_pip}" ', 1)
        elif cmd.startswith("python "):
            isolated_cmd = cmd.replace("python ", f'"{venv_python}" ', 1)

        print(f"Running command [{idx}/{len(commands)}]: {cmd}")
        try:
            res = subprocess.run(  # nosec B602
                isolated_cmd,
                shell=True,
                cwd=sandbox_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=90.0,
                check=False,
            )
            results.append(
                {
                    "command": cmd,
                    "isolated_command": isolated_cmd,
                    "exit_code": res.returncode,
                    "stdout": res.stdout,
                    "stderr": res.stderr,
                }
            )

            if res.returncode != 0:
                print(f"  [!] Failed (exit code: {res.returncode})")
                break
        except subprocess.TimeoutExpired:
            print("  [!] Command timed out (limit: 90s)")
            results.append(
                {
                    "command": cmd,
                    "isolated_command": isolated_cmd,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": "Command timed out",
                }
            )
            break
        except (OSError, ValueError, RuntimeError) as e:
            print(f"  [!] Failed to execute: {e}")
            results.append(
                {
                    "command": cmd,
                    "isolated_command": isolated_cmd,
                    "exit_code": -2,
                    "stdout": "",
                    "stderr": str(e),
                }
            )
            break

    return results


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Extract README instructions and test them in a temporary isolated "
            "virtualenv."
        )
    )
    parser.add_argument(
        "readme_file",
        nargs="?",
        default="README.md",
        help="Path to the README file to test (default: README.md).",
    )
    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Parse and print setup instructions without executing them.",
    )

    args = parser.parse_args()

    readme_path = os.path.abspath(args.readme_file)
    if not os.path.exists(readme_path):
        print(f"Error: README file not found: {readme_path}", file=sys.stderr)
        sys.exit(1)

    print("========================================================================")
    print("README DOCTOR: ISOLATED SETUP AUDITOR")
    print("========================================================================")
    print(f"Auditing: {readme_path}")
    print("Parsing documentation command instructions...")

    commands = extract_commands(readme_path)

    if not commands:
        print("\n[-] No executable commands parsed from code blocks.")
        sys.exit(0)

    print(f"Parsed {len(commands)} commands:")
    for idx, cmd in enumerate(commands, 1):
        print(f"  {idx}. {cmd}")
    print("-" * 80)

    if args.dry_run:
        print("[+] Dry-run completed. Skip execution runs.")
        sys.exit(0)

    # Setup temp sandbox
    with tempfile.TemporaryDirectory() as sandbox_dir:
        results = create_venv_and_run(commands, sandbox_dir)

    print("\n" + "=" * 80)
    print("ISOLATED DIAGNOSTICS REPORT:")
    print("=" * 80)

    failed = False
    for idx, res in enumerate(results, 1):
        status = "PASSED" if res["exit_code"] == 0 else "FAILED"
        print(f"Command {idx}: {res['command']}")
        print(f"Status:    {status} (Exit Code: {res['exit_code']})")
        if res["exit_code"] != 0:
            failed = True
            print("Stderr Logs:")
            print(res["stderr"].strip())
            print("Stdout Logs:")
            print(res["stdout"].strip())
            print("-" * 80)
            break
        print("-" * 80)

    if failed:
        print("\n[!] README Doctor: Flagged stale or broken installation instructions.")
        sys.exit(1)
    else:
        print(
            "\n[+] Success: README setup instructions successfully verified in "
            "isolated environment."
        )


if __name__ == "__main__":
    main()
