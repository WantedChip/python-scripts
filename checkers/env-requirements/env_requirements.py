#!/usr/bin/env python3
"""Env Requirements.

Scans project files recursively to identify environment variables used in source
code, matches them with .env.example definitions, and flags required, undocumented,
or stale settings.
"""

import argparse
import os
import re
import sys
from typing import Any, Dict, Set


def scan_source_env_vars(target_dir: str) -> Dict[str, Dict[str, Any]]:
    """Scan python source files for os.environ and os.getenv queries."""
    found_vars: Dict[str, Dict[str, Any]] = {}
    exclude_dirs = {".git", "venv", ".venv", "build", "dist", "__pycache__"}

    # Pattern for os.environ[...] or os.environ.get(...) or os.getenv(...)
    # Group 1: variable name
    env_pattern = re.compile(
        r"os\.(?:environ(?:.get)?|getenv)\s*\(\s*['\"]([a-zA-Z0-9_]+)['\"]",
        re.IGNORECASE,
    )
    # Pattern for direct brackets access os.environ['KEY']
    bracket_pattern = re.compile(
        r"os\.environ\s*\[\s*['\"]([a-zA-Z0-9_]+)['\"]", re.IGNORECASE
    )

    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            if f.endswith(".py"):
                fpath = os.path.abspath(os.path.join(root, f))
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                        for line_num, line in enumerate(fh, 1):
                            # Check bracket required vars
                            for m in bracket_pattern.finditer(line):
                                var_name = m.group(1)
                                if var_name not in found_vars:
                                    found_vars[var_name] = {
                                        "required": True,
                                        "occurrences": [],
                                    }
                                found_vars[var_name]["occurrences"].append(
                                    (fpath, line_num)
                                )
                                found_vars[var_name]["required"] = True

                            # Check standard access
                            for m in env_pattern.finditer(line):
                                var_name = m.group(1)
                                if var_name not in found_vars:
                                    found_vars[var_name] = {
                                        "required": False,
                                        "occurrences": [],
                                    }
                                found_vars[var_name]["occurrences"].append(
                                    (fpath, line_num)
                                )
                except OSError:
                    pass
    return found_vars


def scan_config_env_vars(file_path: str) -> Set[str]:
    """Parse environment variables defined in .env or .env.example files."""
    vars_set: Set[str] = set()
    if not os.path.exists(file_path):
        return vars_set

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line_strip = line.strip()
                if not line_strip or line_strip.startswith("#"):
                    continue
                # Split on =
                parts = line_strip.split("=", 1)
                if parts:
                    vars_set.add(parts[0].strip())
    except OSError:
        pass
    return vars_set


def scan_docker_compose(file_path: str) -> Set[str]:
    """Parse environment variables defined in docker-compose.yml files."""
    vars_set: Set[str] = set()
    if not os.path.exists(file_path):
        return vars_set

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        # Find matches for environment: section or variables mapping
        matches = re.findall(r"\b([a-zA-Z0-9_]+)\s*:", content)
        for m in matches:
            if m.isupper():
                vars_set.add(m)
    except OSError:
        pass
    return vars_set


# pylint: disable=too-many-locals
def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Scan codebase for required, undocumented, or stale environment variables."
        )
    )
    parser.add_argument(
        "target_dir",
        nargs="?",
        default=".",
        help="Code directory path to scan recursively (default: current directory).",
    )

    args = parser.parse_args()

    target_dir = os.path.abspath(args.target_dir)
    if not os.path.exists(target_dir):
        print(f"Error: Path does not exist: {target_dir}", file=sys.stderr)
        sys.exit(1)

    print("========================================================================")
    print("ENVIRONMENT REQUIREMENTS AUDITOR")
    print("========================================================================")
    print(f"Codebase Target: {target_dir}")
    print("Scanning python files, Dockerfiles, compose mappings, and .env.examples...")
    print("-" * 80)

    # 1. Scan source code
    source_vars = scan_source_env_vars(target_dir)

    # 2. Scan configurations
    example_path = os.path.join(target_dir, ".env.example")
    example_vars = scan_config_env_vars(example_path)

    # Scan Docker compose
    compose_path = os.path.join(target_dir, "docker-compose.yml")
    docker_vars = scan_docker_compose(compose_path)

    # Combined config declarations
    config_declared = example_vars | docker_vars

    # Analyze status
    report_rows = []

    # Check variables found in source
    for name, info in source_vars.items():
        required = "Required" if info["required"] else "Optional"
        status = "Documented"
        if name not in config_declared:
            status = "Undocumented (Missing from config)"

        # Get first occurrence relative path
        first_ref = "Unknown"
        if info["occurrences"]:
            rel = os.path.relpath(info["occurrences"][0][0], target_dir)
            ref_line = info["occurrences"][0][1]
            first_ref = f"{rel}:{ref_line}"

        report_rows.append(
            {
                "name": name,
                "required": required,
                "status": status,
                "reference": first_ref,
            }
        )

    # Check stale variables (defined in examples but never used in source)
    for name in config_declared:
        if name not in source_vars:
            report_rows.append(
                {
                    "name": name,
                    "required": "N/A",
                    "status": "Stale (Declared but unused in source)",
                    "reference": "N/A",
                }
            )

    if not report_rows:
        print(
            "\n[+] Success: No environment variables detected in source code or "
            "configuration files."
        )
        sys.exit(0)

    # Sort report rows: Undocumented first, then Stale, then Required, then Documented
    def sort_key(row: Dict[str, Any]) -> int:
        status: str = row["status"]
        if "Undocumented" in status:
            return 1
        if "Stale" in status:
            return 2
        if row["required"] == "Required":
            return 3
        return 4

    report_rows.sort(key=sort_key)

    print(f"\nFlagged {len(report_rows)} environment variables details:")
    print("=" * 80)
    hdr = (
        f"{'VARIABLE NAME':<25} | {'REQUIRED':<10} | {'STATUS':<32} | "
        f"{'FIRST REFERENCED'}"
    )
    print(hdr)
    print("-" * 80)
    for row in report_rows:
        row_fmt = (
            f"{row['name']:<25} | {row['required']:<10} | {row['status']:<32} | "
            f"{row['reference']}"
        )
        print(row_fmt)
    print("=" * 80)


if __name__ == "__main__":
    main()
