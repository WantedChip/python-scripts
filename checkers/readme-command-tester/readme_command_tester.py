#!/usr/bin/env python3
"""README Command Tester.

Parses README.md file, extracts shell command blocks (sh, bash, cmd, powershell),
runs them inside a temporary workspace directory, and checks for failures.
"""

import argparse
import os
import re
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from typing import Any, Dict, List


def extract_readme_commands(readme_path: str) -> List[str]:
    """Parse README file and extract executable shell code lines from code blocks."""
    commands: List[str] = []
    if not os.path.exists(readme_path):
        return commands

    try:
        with open(readme_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return commands

    # Regex to find code blocks with shell-like languages
    # Group 1: language, Group 2: code block content
    block_pattern = re.compile(
        r"```(bash|sh|shell|powershell|cmd|console)\n(.*?)\n```",
        re.DOTALL | re.IGNORECASE,
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

            # Handle typical command prompts ($ git clone..., > python manage...)
            if line_strip.startswith("$ "):
                line_strip = line_strip[2:]
            elif line_strip.startswith("> "):
                line_strip = line_strip[2:]

            commands.append(line_strip)

    return commands


def run_commands_in_sandbox(
    commands: List[str], sandbox_dir: str
) -> List[Dict[str, Any]]:
    """Execute command lines in sequence within the temporary sandbox folder."""
    results = []

    # Copy files from current directory to sandbox
    curr_dir = os.getcwd()
    for item in os.listdir(curr_dir):
        # Avoid recursive copying of sandbox if inside current dir
        if os.path.abspath(item) == os.path.abspath(sandbox_dir):
            continue
        # Skip directories like .git, node_modules, env, etc.
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

    for idx, cmd in enumerate(commands, 1):
        print(f"Running command [{idx}/{len(commands)}]: {cmd}")
        try:
            res = subprocess.run(  # nosec B602
                cmd,
                shell=True,
                cwd=sandbox_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60.0,
                check=False,
            )
            results.append(
                {
                    "command": cmd,
                    "exit_code": res.returncode,
                    "stdout": res.stdout,
                    "stderr": res.stderr,
                }
            )

            if res.returncode != 0:
                print(f"  [!] Failed with exit code {res.returncode}")
                # Stop on first setup error
                break
        except subprocess.TimeoutExpired:
            print("  [!] Command timed out (limit: 60s)")
            results.append(
                {
                    "command": cmd,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": "Execution timed out",
                }
            )
            break
        except (OSError, ValueError, RuntimeError) as e:
            print(f"  [!] Execution failed: {e}")
            results.append(
                {"command": cmd, "exit_code": -2, "stdout": "", "stderr": str(e)}
            )
            break

    return results


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Verify README shell command blocks inside an isolated temp sandbox."
        )
    )
    parser.add_argument(
        "readme_file",
        nargs="?",
        default="README.md",
        help="Path to the target README file to test (default: README.md).",
    )
    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Parse and print commands without executing them.",
    )

    args = parser.parse_args()

    readme_path = os.path.abspath(args.readme_file)
    if not os.path.exists(readme_path):
        print(f"Error: README file not found: {readme_path}", file=sys.stderr)
        sys.exit(1)

    print("========================================================================")
    print("README COMMAND TESTER: SETUP VERIFICATION LINTER")
    print("========================================================================")
    print(f"Auditing file: {readme_path}")
    print("Extracting setup instructions...")

    commands = extract_readme_commands(readme_path)

    if not commands:
        print("\n[-] No executable console/shell code blocks discovered in README.")
        sys.exit(0)

    print(f"Extracted {len(commands)} commands:")
    for idx, cmd in enumerate(commands, 1):
        print(f"  {idx}. {cmd}")
    print("-" * 80)

    if args.dry_run:
        print("[+] Dry-run completed. Skip execution diagnostics.")
        sys.exit(0)

    # Setup isolated sandbox
    with tempfile.TemporaryDirectory() as sandbox_dir:
        print(f"Executing commands inside sandbox: {sandbox_dir}")
        results = run_commands_in_sandbox(commands, sandbox_dir)

    print("\n" + "=" * 80)
    print("EXECUTION DIAGNOSTICS REPORT:")
    print("=" * 80)

    failed = False
    for idx, res in enumerate(results, 1):
        status = "PASSED" if res["exit_code"] == 0 else "FAILED"
        print(f"Command {idx}: {res['command']}")
        print(f"Status:    {status} (Exit Code: {res['exit_code']})")
        if res["exit_code"] != 0:
            failed = True
            print("Stderr Details:")
            print(res["stderr"].strip())
            print("Stdout Logs:")
            print(res["stdout"].strip())
            print("-" * 80)
            break
        print("-" * 80)

    if failed:
        print("\n[!] Setup check FAILED. Stale or invalid instruction in README.")
        sys.exit(1)
    else:
        print("\n[+] Success: All README commands executed cleanly (exit code 0).")


if __name__ == "__main__":
    main()
