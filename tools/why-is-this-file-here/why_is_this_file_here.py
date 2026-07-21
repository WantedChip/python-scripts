#!/usr/bin/env python3
"""Why is this File Here.

Audits git logs, import linkages, build rules, and gitignore overrides for a
file path to explain its origin, current references, and deletion safety.
"""

import argparse
import os
import subprocess  # nosec B404
import sys
from typing import List, Tuple


def is_git_repo(path: str) -> bool:
    """Verify if target folder lies inside a Git repository."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec B607, B603
        return res.returncode == 0
    except OSError:
        return False


def get_git_origin(file_path: str, repo_path: str) -> Tuple[str, str]:
    """Find the commit SHA, author, and description that first introduced the file."""
    rel_path = os.path.relpath(file_path, repo_path)
    try:
        res = subprocess.run(
            [
                "git",
                "log",
                "--follow",
                "--diff-filter=A",
                "--format=%H|%an|%cr|%s",
                "--",
                rel_path,
            ],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec B607, B603
        lines = [line.strip() for line in res.stdout.split("\n") if line.strip()]
        if lines:
            parts = lines[-1].split("|", 3)
            if len(parts) >= 4:
                return parts[0][:8], f"{parts[1]} ({parts[2]}) - {parts[3]}"
    except (OSError, subprocess.SubprocessError):
        pass
    return "Unknown", "No creation details logged in git history."


def get_last_modified(file_path: str, repo_path: str) -> str:
    """Find details of the latest commit modifying this file."""
    rel_path = os.path.relpath(file_path, repo_path)
    try:
        res = subprocess.run(
            ["git", "log", "-n", "1", "--format=%H|%an|%cr|%s", "--", rel_path],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec B607, B603
        parts = res.stdout.strip().split("|", 3)
        if len(parts) >= 4:
            return f"{parts[0][:8]} by {parts[1]} ({parts[2]}) - {parts[3]}"
    except (OSError, subprocess.SubprocessError):
        pass
    return "Unknown last modify log."


def check_is_ignored(file_path: str, repo_path: str) -> bool:
    """Check if the file matches any active gitignore rules."""
    rel_path = os.path.relpath(file_path, repo_path)
    try:
        res = subprocess.run(
            ["git", "check-ignore", "-q", rel_path],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )  # nosec B607, B603
        return res.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


Reference = Tuple[str, int]


# pylint: disable=too-many-locals
def find_code_references(file_path: str, repo_path: str) -> List[Reference]:
    """Scan all text files in the project to search for basenames or relative
    path strings.
    """
    refs = []
    base_name = os.path.basename(file_path)
    base_no_ext = os.path.splitext(base_name)[0]

    exclude_dirs = {
        ".git",
        "venv",
        ".venv",
        "node_modules",
        "build",
        "dist",
        "__pycache__",
    }
    exclude_exts = {
        ".png",
        ".jpg",
        ".zip",
        ".tar",
        ".gz",
        ".exe",
        ".pdf",
        ".db",
        ".sqlite",
    }

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            full_f = os.path.join(root, f)
            if full_f == file_path:
                continue

            ext = os.path.splitext(f)[1].lower()
            if ext in exclude_exts:
                continue

            try:
                with open(full_f, "r", encoding="utf-8", errors="replace") as fh:
                    for line_num, line in enumerate(fh, 1):
                        if base_name in line or (
                            base_no_ext and f"import {base_no_ext}" in line
                        ):
                            rel_ref = os.path.relpath(full_f, repo_path)
                            refs.append((rel_ref, line_num))
            except OSError:
                pass
    return refs[:10]


# pylint: disable=too-many-locals,too-many-branches,too-many-statements
def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Trace a file's Git creation history, import dependencies, and "
            "ignore status."
        )
    )
    parser.add_argument("file_path", help="Target file path to analyze.")

    args = parser.parse_args()

    fpath = os.path.abspath(args.file_path)
    if not os.path.exists(fpath):
        print(f"Error: File does not exist: {fpath}", file=sys.stderr)
        sys.exit(1)

    repo_path = os.getcwd()
    in_git = is_git_repo(repo_path)

    print("========================================================================")
    print("WHY IS THIS FILE HERE? FILE HISTORY & RELATIONSHIP SNIFFER")
    print("========================================================================")
    print(f"File Path: {os.path.relpath(fpath, repo_path)}")
    print("-" * 80)

    print("GIT HISTORY STATS:")
    if in_git:
        sha, desc = get_git_origin(fpath, repo_path)
        last_mod = get_last_modified(fpath, repo_path)
        print(f"  First Introduced in: {sha}")
        print(f"  Creation details:    {desc}")
        print(f"  Latest modification: {last_mod}")
    else:
        print(
            "  [!] Target path not inside a Git repository. Cannot query history logs."
        )
    print("-" * 80)

    print("IGNORE STATUS:")
    is_ignored = check_is_ignored(fpath, repo_path) if in_git else False
    print(
        f"  Matches gitignore rules: {'Yes (File is ignored)' if is_ignored else 'No'}"
    )
    print("-" * 80)

    print("CODEBASE REFERENCES:")
    references = find_code_references(fpath, repo_path)
    if references:
        print(f"  Discovered references in {len(references)} locations:")
        for ref_file, line in references:
            print(f"    - {ref_file} (Line: {line})")
    else:
        print("  No import or string occurrences found in other codebase files.")
    print("-" * 80)

    print("GENERATED / STALE FILE ESTIMATION:")
    is_generated = False

    parts = fpath.split(os.sep)
    if any(p in ("build", "dist", "target", "out", "__pycache__") for p in parts):
        is_generated = True
        print("  - File lies inside standard build/distribution folders.")

    try:
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            top = f.read(1000).lower()
            if any(
                term in top
                for term in ("generated by", "auto-generated", "do not edit")
            ):
                is_generated = True
                print("  - Header comments contain auto-generator warnings.")
    except OSError:
        pass

    if not is_generated:
        print("  - File appears to be a manually written codebase asset.")
    print("-" * 80)

    print("DELETION SAFETY DIAGNOSTIC:")
    if not references:
        if is_ignored or is_generated:
            msg = (
                "  [Safety Rating: HIGH] File is unused, ignored, or generated. "
                "Safe to remove."
            )
            print(msg)
        else:
            msg = (
                "  [Safety Rating: MEDIUM] No references found, but file is not "
                "ignored. Verify before deleting."
            )
            print(msg)
    else:
        msg = (
            "  [Safety Rating: LOW] Active references found inside codebase "
            "files. Removal may break execution."
        )
        print(msg)
    print("========================================================================")


if __name__ == "__main__":
    main()
