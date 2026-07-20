#!/usr/bin/env python3
"""Commit Surgeon.

Analyzes Git working tree modifications, maps dependencies among changed files,
and suggests organized commit groups to split large monolithic commits.
"""

import argparse
import os
import re
import subprocess  # nosec B404
import sys
from typing import Dict, List, Set


def is_git_repo(path: str) -> bool:
    """Verify if target path lies inside a Git repository."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec
        return res.returncode == 0
    except OSError:
        return False


def get_modified_files(repo_path: str) -> List[str]:
    """Parse git status --porcelain to gather modified or untracked files."""
    files = []
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec
        for line in res.stdout.split("\n"):
            if len(line) > 3:
                path = line[3:].strip()
                if " -> " in path:
                    path = path.split(" -> ")[1].strip()
                files.append(path)
    except (OSError, ValueError):
        pass
    return files


def extract_imports(file_path: str) -> Set[str]:
    """Parse file imports (Python/JS imports) to trace codebase dependencies."""
    imports: Set[str] = set()
    if not os.path.exists(file_path):
        return imports

    py_import_pattern = re.compile(
        r"^\s*(?:import|from)\s+([a-zA-Z0-9_\.]+)", re.MULTILINE
    )
    js_import_pattern = re.compile(
        r"^\s*(?:import|require)\s*\(?\s*['\"](?:\./)?([a-zA-Z0-9_\-\./]+)['\"]",
        re.MULTILINE,
    )

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
            for m in py_import_pattern.finditer(content):
                parts = m.group(1).split(".")
                imports.add(parts[0])
            for m in js_import_pattern.finditer(content):
                base = os.path.basename(m.group(1))
                imports.add(base)
    except OSError:
        pass
    return imports


def map_dependencies(repo_path: str, modified_files: List[str]) -> Dict[str, Set[str]]:
    """Build a dependency mapping among modified files based on import lookups."""
    deps: Dict[str, Set[str]] = {}
    mod_basenames = {os.path.basename(f): f for f in modified_files}

    for f in modified_files:
        full_path = os.path.join(repo_path, f)
        deps[f] = set()

        file_imports = extract_imports(full_path)
        for imp in file_imports:
            for bname, mod_path in mod_basenames.items():
                bname_no_ext = os.path.splitext(bname)[0]
                if imp in (bname_no_ext, bname):
                    deps[f].add(mod_path)
    return deps


# pylint: disable=too-many-locals,too-many-branches,too-many-statements
def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Analyze messy git working trees to suggest logical commit "
            "staging groups."
        )
    )
    parser.add_argument(
        "repo_path",
        nargs="?",
        default=".",
        help="Git repository path to inspect (default: current directory).",
    )

    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo_path)
    if not os.path.exists(repo_path):
        print(f"Error: Path does not exist: {repo_path}", file=sys.stderr)
        sys.exit(1)

    if not is_git_repo(repo_path):
        print(f"Error: '{repo_path}' is not inside a Git repository.", file=sys.stderr)
        sys.exit(1)

    print("========================================================================")
    print("COMMIT SURGEON: LOGICAL GIT COMMIT STAGER")
    print("========================================================================")
    print(f"Repository Path: {repo_path}")
    print("Scanning git status and changed files dependencies...")
    print("-" * 80)

    modified = get_modified_files(repo_path)
    if not modified:
        print("\n[+] Working tree clean. No dirty changes to inspect.")
        sys.exit(0)

    print(f"Found {len(modified)} dirty/untracked files.")

    deps = map_dependencies(repo_path, modified)

    group_configs = []
    group_core = []
    group_app = []
    group_tests = []

    for f in modified:
        base = os.path.basename(f)
        ext = os.path.splitext(f)[1].lower()

        if base in (
            "package.json",
            "package-lock.json",
            "requirements.txt",
            "pyproject.toml",
            "setup.py",
            "docker-compose.yml",
            ".gitignore",
            "README.md",
        ):
            group_configs.append(f)
        elif "test" in f or "tests" in f or ext == ".md":
            group_tests.append(f)
        else:
            imports_others = len(deps.get(f, set())) > 0
            is_imported_by_others = False
            for _, other_deps in deps.items():
                if f in other_deps:
                    is_imported_by_others = True
                    break

            if is_imported_by_others and not imports_others:
                group_core.append(f)
            else:
                group_app.append(f)

    print("\nSUGGESTED COMMIT GROUPS:")
    print("=" * 80)

    commit_idx = 1

    if group_configs:
        print(f"Commit {commit_idx}: Project configurations & dependencies updates")
        print(f"  Files ({len(group_configs)}):")
        for f in group_configs:
            print(f"    - {f}")
        print("  Staging command:")
        cmd_cfg = (
            f"    git add {' '.join(group_configs)} && git commit -m "
            '"chore: update configurations and manifests"'
        )
        print(cmd_cfg)
        print("-" * 80)
        commit_idx += 1

    if group_core:
        print(f"Commit {commit_idx}: Core components & helper files")
        print(f"  Files ({len(group_core)}):")
        for f in group_core:
            print(f"    - {f}")
        print("  Staging command:")
        cmd_core = (
            f"    git add {' '.join(group_core)} && git commit -m "
            '"refactor: implement core codebase models and helpers"'
        )
        print(cmd_core)
        print("-" * 80)
        commit_idx += 1

    if group_app:
        print(f"Commit {commit_idx}: Feature implementation & application logic")
        print(f"  Files ({len(group_app)}):")
        for f in group_app:
            print(f"    - {f}")
        print("  Staging command:")
        cmd_app = (
            f"    git add {' '.join(group_app)} && git commit -m "
            '"feat: implement main application features and logic"'
        )
        print(cmd_app)
        print("-" * 80)
        commit_idx += 1

    if group_tests:
        print(f"Commit {commit_idx}: Tests and Documentation updates")
        print(f"  Files ({len(group_tests)}):")
        for f in group_tests:
            print(f"    - {f}")
        print("  Staging command:")
        cmd_tst = (
            f"    git add {' '.join(group_tests)} && git commit -m "
            '"test: implement test cases and update readme docs"'
        )
        print(cmd_tst)
        print("=" * 80)

    print(
        "\nHint: stage files selectively in small blocks to keep Git histories clean."
    )


if __name__ == "__main__":
    main()
