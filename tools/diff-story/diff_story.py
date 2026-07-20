#!/usr/bin/env python3
"""Diff Story.

Parses Git patch/diff files and outputs a narrative structured summary:
behavioral changes, refactors, dependency updates, configuration edits,
and risk warnings.
"""

import argparse
import os
import re
import subprocess  # nosec B404
import sys
from typing import Any, Dict, List, Optional, Tuple


def get_git_diff(repo_path: str) -> Optional[str]:
    """Retrieve active git diff patch from the target repository directory."""
    try:
        res = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout
    except (OSError, ValueError):
        pass
    return None


# pylint: disable=too-many-locals,too-many-branches,too-many-statements
def parse_diff_contents(diff_text: str) -> Dict[str, Any]:
    """Parse diff text, mapping file modifications and identifying patterns."""
    dependencies: List[str] = []
    configs: List[str] = []
    refactors: List[str] = []
    risks: List[Tuple[str, str]] = []
    behavioral: List[str] = []

    story: Dict[str, Any] = {
        "files_count": 0,
        "additions": 0,
        "deletions": 0,
        "dependencies": dependencies,
        "configs": configs,
        "refactors": refactors,
        "risks": risks,
        "behavioral": behavioral,
    }

    chunks = diff_text.split("diff --git ")
    for chunk in chunks:
        if not chunk.strip():
            continue

        lines = chunk.split("\n")
        header = lines[0]
        match = re.search(r"a/(.+?)\s+b/", header)
        if not match:
            continue

        fpath = match.group(1)
        story["files_count"] += 1

        added_lines = 0
        deleted_lines = 0
        has_imports = False
        has_configs = False
        has_refactor_cues = False
        has_security_keywords = False

        for line in lines:
            if line.startswith("+++") or line.startswith("---"):
                continue
            if line.startswith("+"):
                added_lines += 1
                story["additions"] += 1
                if any(x in line for x in ("import ", "require(", "from ")):
                    has_imports = True
                if any(x in line for x in ("=", ":")) and any(
                    y in line.lower()
                    for y in ("port", "host", "timeout", "key", "secret", "token")
                ):
                    has_configs = True
                if any(
                    x in line.lower()
                    for x in (
                        "password",
                        "crypto",
                        "auth",
                        "login",
                        "encrypt",
                        "decrypt",
                        "token",
                    )
                ):
                    has_security_keywords = True
            elif line.startswith("-"):
                deleted_lines += 1
                story["deletions"] += 1
                if "def " in line or "function " in line:
                    has_refactor_cues = True

        base_name = os.path.basename(fpath).lower()

        # 1. Dependencies
        if (
            base_name in ("requirements.txt", "package.json", "setup.py", "pipfile")
            or has_imports
        ):
            dependencies.append(fpath)

        # 2. Configs
        elif (
            any(
                fpath.endswith(ext)
                for ext in (".yaml", ".yml", ".json", ".toml", ".ini", ".env")
            )
            or has_configs
        ):
            configs.append(fpath)

        # 3. Risks
        if (
            any(
                x in fpath.lower()
                for x in ("auth", "security", "crypt", "db", "database")
            )
            or has_security_keywords
        ):
            risks.append(
                (fpath, "Modifications touch security/auth or credentials domains")
            )
        elif added_lines > 150 or deleted_lines > 150:
            high_vol_msg = (
                f"High volume edits (Added: {added_lines}, Deleted: {deleted_lines})"
            )
            risks.append((fpath, high_vol_msg))

        # 4. Refactoring
        if (
            has_refactor_cues
            or "refactor" in chunk.lower()
            or "rename" in chunk.lower()
        ):
            refactors.append(fpath)

        # 5. Behavioral logic changes
        if fpath.endswith((".py", ".js", ".ts", ".go", ".rs", ".java", ".cpp")):
            if fpath not in dependencies and fpath not in refactors:
                behavioral.append(fpath)

    return story


# pylint: disable=too-many-branches,too-many-statements
def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description="Compile a narrative behavior and risk summary of Git diff patches."
    )
    parser.add_argument(
        "diff_file",
        nargs="?",
        help=(
            "Path to file containing git diff patch. If omitted, diff is read "
            "from local workspace."
        ),
    )

    args = parser.parse_args()

    diff_content = None
    if args.diff_file:
        path = os.path.abspath(args.diff_file)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    diff_content = f.read()
            except OSError as e:
                print(f"Error reading diff file: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            print(f"Error: Diff file not found: {path}", file=sys.stderr)
            sys.exit(1)
    else:
        diff_content = get_git_diff(".")
        if not diff_content:
            print(
                "Error: No active Git changes found or stdin/file not provided.",
                file=sys.stderr,
            )
            sys.exit(1)

    print("========================================================================")
    print("DIFF STORY: GIT PATCH NARRATIVE GENERATOR")
    print("========================================================================")

    story = parse_diff_contents(diff_content)

    print(f"FILES IMPACTED: {story['files_count']}")
    additions = story["additions"]
    deletions = story["deletions"]
    print(f"METRICS:        +{additions} insertions, -{deletions} deletions")
    print("-" * 80)

    # 1. Dependency modifications
    print("DEPENDENCY CHANGES:")
    if not story["dependencies"]:
        print("  No dependency updates or import declarations added.")
    else:
        for d in story["dependencies"]:
            print(f"  - {d}")
    print("-" * 80)

    # 2. Config modifications
    print("CONFIGURATION EDITS:")
    if not story["configs"]:
        print("  No settings config adjustments found.")
    else:
        for c in story["configs"]:
            print(f"  - {c}")
    print("-" * 80)

    # 3. Refactoring changes
    print("REFACTORS IDENTIFIED:")
    if not story["refactors"]:
        print("  No obvious refactoring blocks/renames discovered.")
    else:
        for r in story["refactors"]:
            print(f"  - {r}")
    print("-" * 80)

    # 4. Behavioral Logic Changes
    print("BEHAVIORAL LOGIC CHANGES:")
    if not story["behavioral"]:
        print("  No direct business logic modifications scanned.")
    else:
        for b in story["behavioral"]:
            print(f"  - {b}")
    print("-" * 80)

    # 5. Risk Alerts
    print("HIGH RISK WARNINGS:")
    if not story["risks"]:
        print("  [+] Low risk level. No sensitive/critical areas modified.")
    else:
        for f, reason in story["risks"]:
            print(f"  [!] {f}: {reason}")
    print("========================================================================")


if __name__ == "__main__":
    main()
