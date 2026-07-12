#!/usr/bin/env python3
"""Run mypy once per containing directory, not one batch across the repo.

Standalone script folders in this repo have no package structure
(deliberately — see .agents/guidelines.md Section 1) and use kebab-case
folder names, so two different scripts can share a filename (e.g. two
vulture_whitelist.py files) with nothing to disambiguate them. Passing all
matched files to a single mypy invocation makes mypy try to assign both
the same module name and fail with "Duplicate module named X". Looping
per directory sidesteps that entirely: files within one script folder are
safe to check together, but different folders never share an invocation,
so they can never collide.

Used as a pre-commit `language: system` local hook entry point; pre-commit
calls this with the list of matched files as argv. Mirrors the equivalent
per-directory loop in .github/workflows/ci.yml's mypy step.
"""

import subprocess  # nosec B404 - used to invoke mypy directly; no shell involved
import sys
from collections import defaultdict
from pathlib import Path


def main() -> int:
    """Group the given files by parent directory and run mypy per group."""
    files = [Path(f) for f in sys.argv[1:]]
    if not files:
        return 0

    by_dir: dict[Path, list[Path]] = defaultdict(list)
    for file_path in files:
        by_dir[file_path.parent].append(file_path)

    failures = 0
    for directory in sorted(by_dir):
        group = by_dir[directory]
        cmd = ["mypy", "--config-file=mypy.ini", *[str(f) for f in group]]
        print(f"-- mypy: {directory} --")
        # No shell=True; cmd is a list, and the inputs are the mypy config
        # path plus file paths pre-commit itself already matched (git-tracked
        # files) — not externally supplied or untrusted input.
        result = subprocess.run(cmd, check=False)  # nosec B603
        if result.returncode != 0:
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
