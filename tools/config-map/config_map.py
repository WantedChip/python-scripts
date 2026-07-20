#!/usr/bin/env python3
"""Config Map.

Scans project files recursively to identify configuration variables used in CLI
arguments, environment variable lookups, settings files, and maps precedence.
"""

import argparse
import os
import re
import sys
from typing import Any, Dict, List


# pylint: disable=too-many-locals
def scan_cli_arguments(target_dir: str) -> List[Dict[str, Any]]:
    """Scan codebases for argparse argument definitions."""
    cli_args = []
    exclude_dirs = {".git", "venv", ".venv", "build", "dist", "__pycache__"}

    # Regex to find parser.add_argument(...)
    arg_pattern = re.compile(
        r"\.add_argument\s*\(\s*['\"](-{1,2}[a-zA-Z0-9_\-]+)['\"]\s*"
        r"(?:,\s*['\"](-{1,2}[a-zA-Z0-9_\-]+)['\"])?[^)]*\)",
        re.DOTALL,
    )

    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            if f.endswith(".py"):
                fpath = os.path.join(root, f)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                        content = fh.read()
                        for m in arg_pattern.finditer(content):
                            primary = m.group(1)
                            alt = m.group(2) or ""
                            default_val = "N/A"
                            default_match = re.search(
                                r"default\s*=\s*([^,\s)]+)", m.group(0)
                            )
                            if default_match:
                                default_val = (
                                    default_match.group(1)
                                    .replace("'", "")
                                    .replace('"', "")
                                )

                            cli_args.append(
                                {
                                    "file": os.path.relpath(fpath, target_dir),
                                    "flag": f"{primary} / {alt}" if alt else primary,
                                    "name": primary.replace("-", ""),
                                    "default": default_val,
                                }
                            )
                except OSError:
                    pass
    return cli_args


# pylint: disable=too-many-locals
def scan_env_variables(target_dir: str) -> List[Dict[str, Any]]:
    """Scan codebases for environment variables (os.environ, os.getenv)."""
    env_vars = []
    exclude_dirs = {".git", "venv", ".venv", "build", "dist", "__pycache__"}

    env_pattern = re.compile(
        r"os\.(?:environ(?:.get)?|getenv)\s*\(\s*['\"]([a-zA-Z0-9_]+)['\"]"
        r"(?:\s*,\s*([^)]+))?",
        re.IGNORECASE,
    )
    bracket_pattern = re.compile(
        r"os\.environ\s*\[\s*['\"]([a-zA-Z0-9_]+)['\"]", re.IGNORECASE
    )

    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            if f.endswith(".py"):
                fpath = os.path.join(root, f)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                        for line_num, line in enumerate(fh, 1):
                            for m in bracket_pattern.finditer(line):
                                var_name = m.group(1)
                                env_vars.append(
                                    {
                                        "file": os.path.relpath(fpath, target_dir),
                                        "line": line_num,
                                        "name": var_name,
                                        "default": (
                                            "None (Required/Throws KeyException)"
                                        ),
                                    }
                                )
                            for m in env_pattern.finditer(line):
                                var_name = m.group(1)
                                default_val = (
                                    m.group(2).strip() if m.group(2) else "None"
                                )
                                default_val = default_val.replace("'", "").replace(
                                    '"', ""
                                )
                                env_vars.append(
                                    {
                                        "file": os.path.relpath(fpath, target_dir),
                                        "line": line_num,
                                        "name": var_name,
                                        "default": default_val,
                                    }
                                )
                except OSError:
                    pass
    return env_vars


def scan_file_configurations(target_dir: str) -> List[Dict[str, Any]]:
    """Scan codebases for JSON, YAML, TOML config loaders."""
    configs = []
    exclude_dirs = {".git", "venv", ".venv", "build", "dist", "__pycache__"}

    loader_pattern = re.compile(
        r"(?:json|yaml|toml|yaml\.safe_load)\s*\.\s*(?:load|loads|safe_load)"
        r"\s*\(\s*([^)]+)\)",
        re.IGNORECASE,
    )

    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            if f.endswith(".py"):
                fpath = os.path.join(root, f)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                        for line_num, line in enumerate(fh, 1):
                            for m in loader_pattern.finditer(line):
                                configs.append(
                                    {
                                        "file": os.path.relpath(fpath, target_dir),
                                        "line": line_num,
                                        "loader": m.group(0).strip(),
                                        "source": m.group(1).strip(),
                                    }
                                )
                except OSError:
                    pass
    return configs


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Inspect codebase to compile a map of CLI, env, and settings "
            "configurations."
        )
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Folder to scan recursively (default: current directory).",
    )

    args = parser.parse_args()

    target_dir = os.path.abspath(args.directory)
    if not os.path.exists(target_dir):
        print(f"Error: Path does not exist: {target_dir}", file=sys.stderr)
        sys.exit(1)

    print("========================================================================")
    print("CONFIG MAP: RESOLUTION HIERARCHY")
    print("========================================================================")
    print(f"Directory: {target_dir}")
    print("Mapping configuration sources...")
    print("-" * 80)

    # 1. Scan inputs
    cli_args = scan_cli_arguments(target_dir)
    env_vars = scan_env_variables(target_dir)
    file_configs = scan_file_configurations(target_dir)

    # 2. Output CLI Arguments
    print(f"1. CLI ARGUMENTS DETECTED ({len(cli_args)}):")
    if not cli_args:
        print("   No standard argparse arguments found.")
    else:
        print(f"   {'FLAG':<22} | {'DEFAULT VALUE':<18} | {'LOCATION'}")
        print("   " + "-" * 75)
        for arg in cli_args:
            print(f"   {arg['flag']:<22} | {arg['default']:<18} | {arg['file']}")
    print("-" * 80)

    # 3. Output Env variables
    print(f"2. ENVIRONMENT VARIABLES DETECTED ({len(env_vars)}):")
    if not env_vars:
        print("   No standard os.environ lookups found.")
    else:
        print(f"   {'VARIABLE KEY':<22} | {'DEFAULT / REQUIREMENT':<25} | {'LOCATION'}")
        print("   " + "-" * 75)
        for ev in env_vars:
            loc = f"{ev['file']}:{ev['line']}"
            print(f"   {ev['name']:<22} | {ev['default']:<25} | {loc}")
    print("-" * 80)

    # 4. Output configuration loaders
    print(f"3. SETTINGS FILE LOADERS DETECTED ({len(file_configs)}):")
    if not file_configs:
        print("   No standard file config loaders found.")
    else:
        print(f"   {'LOADER COMMAND':<32} | {'SOURCE TARGET':<15} | {'LOCATION'}")
        print("   " + "-" * 75)
        for fc in file_configs:
            loc = f"{fc['file']}:{fc['line']}"
            print(f"   {fc['loader'][:32]:<32} | {fc['source'][:15]:<15} | {loc}")
    print("-" * 80)

    # 5. Output Precedence rules
    print("4. STANDARD CONFIG PRECEDENCE RESOLUTION HIERARCHY:")
    print("   [1] Command Line Flags (Overrides all settings)")
    print("   [2] Environment Variables (Overrides file values)")
    print("   [3] File Configurations (Overrides defaults)")
    print("   [4] Built-in Defaults")
    print("========================================================================")


if __name__ == "__main__":
    main()
