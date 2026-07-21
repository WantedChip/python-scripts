#!/usr/bin/env python3
"""Project Resume.

Analyzes an old project folder to extract project scope, execution commands,
last Git modifications, unfinished TODO/FIXME comments, dirty files, likely
entry points, broken dependencies, and next steps.
"""

import argparse
import importlib.util
import json
import os
import re
import subprocess  # nosec B404
import sys
from typing import List, Tuple


def get_project_description(root_path: str) -> str:
    """Analyze README.md or configuration files to determine project scope."""
    readme_paths = ["README.md", "readme.md", "README.txt", "readme.txt"]
    for rp in readme_paths:
        fpath = os.path.join(root_path, rp)
        if os.path.exists(fpath):
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                lines = [line.strip() for line in content.split("\n") if line.strip()]
                summary = []
                for line in lines[:5]:
                    if not line.startswith("#"):
                        summary.append(line)
                    if len(summary) >= 3:
                        break
                if summary:
                    return " ".join(summary)
            except OSError:
                pass

    package_json = os.path.join(root_path, "package.json")
    if os.path.exists(package_json):
        try:
            with open(package_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                desc = data.get("description")
                if desc:
                    return f"NodeJS project: {desc}"
        except (OSError, json.JSONDecodeError):
            pass

    return "No description found. Standard software project folder."


def get_git_history(root_path: str) -> List[str]:
    """Execute git commands to fetch recent changes, dirty files, and active status."""
    history = []
    if not os.path.exists(os.path.join(root_path, ".git")):
        return ["No Git repository history detected."]

    try:
        branch_res = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=root_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec B607, B603
        branch = branch_res.stdout.strip() or "HEAD detached"
        history.append(f"Active Branch: {branch}")

        status_res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec B607, B603
        dirty_files = [
            line.strip() for line in status_res.stdout.split("\n") if line.strip()
        ]
        if dirty_files:
            history.append(f"Dirty/untracked files ({len(dirty_files)}):")
            for df in dirty_files[:5]:
                history.append(f"  - {df}")
            if len(dirty_files) > 5:
                history.append(f"  ... and {len(dirty_files) - 5} more files.")
        else:
            history.append("Working tree clean (no dirty/untracked changes).")

        log_res = subprocess.run(
            ["git", "log", "-n", "5", "--oneline"],
            cwd=root_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec B607, B603
        commits = [line.strip() for line in log_res.stdout.split("\n") if line.strip()]
        if commits:
            history.append("Recent Commits:")
            for c in commits:
                history.append(f"  - {c}")
        else:
            history.append("Recent Commits: None logged")

        ref_res = subprocess.run(
            ["git", "reflog", "-n", "3"],
            cwd=root_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec B607, B603
        ref_logs = [line.strip() for line in ref_res.stdout.split("\n") if line.strip()]
        if ref_logs:
            history.append("Last Git Operations:")
            for r in ref_logs:
                history.append(f"  - {r}")
    except (OSError, subprocess.SubprocessError) as e:
        history.append(f"Could not retrieve Git logs: {e}")

    return history


# pylint: disable=too-many-locals
def scan_todos(root_path: str) -> List[Tuple[str, int, str]]:
    """Scan source files recursively for TODO/FIXME comments."""
    todos = []
    target_exts = {
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".go",
        ".rs",
        ".java",
        ".cpp",
        ".c",
        ".h",
        ".cs",
    }
    exclude_dirs = {
        "node_modules",
        ".git",
        "venv",
        ".venv",
        "build",
        "dist",
        "__pycache__",
    }

    todo_pattern = re.compile(
        r"\b(TODO|FIXME|BUG|XXX)\b\s*[:\-]?\s*(.*)", re.IGNORECASE
    )

    for root, dirs, files in os.walk(root_path):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in target_exts:
                continue

            full_path = os.path.join(root, f)
            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as fh:
                    for line_num, line in enumerate(fh, 1):
                        match = todo_pattern.search(line)
                        if match:
                            tag = match.group(1).upper()
                            details = match.group(2).strip()
                            rel_path = os.path.relpath(full_path, root_path)
                            todos.append((rel_path, line_num, f"{tag}: {details}"))
            except OSError:
                pass

            if len(todos) >= 100:
                break
        if len(todos) >= 100:
            break

    return todos


def get_execution_commands(root_path: str) -> List[str]:
    """Guess execution/running commands from files in folder."""
    commands = []
    pj = os.path.join(root_path, "package.json")
    if os.path.exists(pj):
        commands.append("Node.js package detected:")
        commands.append("  - npm run dev / npm start (Start dev server)")
        commands.append("  - npm test (Run test suites)")

    py_files = [f for f in os.listdir(root_path) if f.endswith(".py")]
    if py_files:
        commands.append("Python project detected:")
        if "manage.py" in py_files:
            commands.append("  - python manage.py runserver (Django server)")
        elif "app.py" in py_files or "main.py" in py_files:
            target = "app.py" if "app.py" in py_files else "main.py"
            commands.append(f"  - python {target} (Execute main application entry)")
        commands.append("  - pytest (Run test cases using pytest)")

    cargo = os.path.join(root_path, "Cargo.toml")
    if os.path.exists(cargo):
        commands.append("Rust Cargo project detected:")
        commands.append("  - cargo run (Compile and run target)")
        commands.append("  - cargo test (Execute cargo test suites)")

    if not commands:
        commands.append("Generic Project (No standard package files recognized).")

    return commands


def check_broken_dependencies(root_path: str) -> List[str]:
    """Check if package requirements are missing or uninstalled in environment."""
    broken: List[str] = []
    req_file = os.path.join(root_path, "requirements.txt")
    if not os.path.exists(req_file):
        return broken

    try:
        with open(req_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line_strip = line.strip()
                if (
                    not line_strip
                    or line_strip.startswith("#")
                    or line_strip.startswith("-")
                ):
                    continue
                parts = re.split(r"==|>=|<=|~=|==|!=|>|<", line_strip)
                if parts:
                    pkg_name = parts[0].strip()
                    if pkg_name.startswith(".") or "/" in pkg_name or "@" in pkg_name:
                        continue
                    spec = importlib.util.find_spec(pkg_name.lower().replace("-", "_"))
                    if spec is None:
                        broken.append(pkg_name)
    except (OSError, ImportError, ValueError):
        pass
    return broken


def find_entry_points(root_path: str) -> List[str]:
    """Scan files recursively to identify main execution entries."""
    entries = []
    target_exts = {".py", ".js", ".ts", ".go", ".rs"}
    exclude_dirs = {
        "node_modules",
        ".git",
        "venv",
        ".venv",
        "build",
        "dist",
        "__pycache__",
    }

    for root, dirs, files in os.walk(root_path):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in target_exts:
                continue

            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, root_path)

            if ext == ".py":
                if f in ("main.py", "app.py", "wsgi.py", "asgi.py"):
                    entries.append(f"{rel_path} (Standard entry name)")
                    continue
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as fh:
                        content = fh.read()
                        if (
                            '__name__ == "__main__"' in content
                            or "__name__ == '__main__'" in content
                        ):
                            entries.append(
                                f"{rel_path} (Contains __main__ scope block)"
                            )
                except OSError:
                    pass
            elif ext in (".js", ".ts"):
                if f in (
                    "index.js",
                    "index.ts",
                    "main.js",
                    "main.ts",
                    "server.js",
                    "app.js",
                ):
                    entries.append(f"{rel_path} (JS/TS entry endpoint)")

    return entries[:5]


# pylint: disable=too-many-branches,too-many-statements
def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description="Resume project context from an old directory."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Target folder directory to analyze (default: current directory).",
    )

    args = parser.parse_args()

    target_dir = os.path.abspath(args.directory)
    if not os.path.exists(target_dir):
        print(f"Error: Path does not exist: {target_dir}", file=sys.stderr)
        sys.exit(1)

    print("========================================================================")
    print("PROJECT RESUME DIAGNOSTIC AUDIT")
    print("========================================================================")
    print(f"Directory: {target_dir}")
    print("-" * 80)

    print("PROJECT SCOPE / DESCRIPTION:")
    print(f"  {get_project_description(target_dir)}")
    print("-" * 80)

    print("LIKELY ENTRY POINTS:")
    entries = find_entry_points(target_dir)
    if entries:
        for ent in entries:
            print(f"  - {ent}")
    else:
        print("  Could not identify standard entry file mappings.")
    print("-" * 80)

    print("HOW TO RUN / EXECUTE COMMANDS:")
    for cmd in get_execution_commands(target_dir):
        print(f"  {cmd}")
    print("-" * 80)

    print("PROJECT MODIFICATIONS & GIT STATUS:")
    for git_line in get_git_history(target_dir):
        print(f"  {git_line}")
    print("-" * 80)

    print("DEPENDENCY CHECK STATUS:")
    broken_deps = check_broken_dependencies(target_dir)
    if broken_deps:
        print(f"  [!] Missing/uninstalled requirements found ({len(broken_deps)}):")
        for bd in broken_deps[:5]:
            print(f"    - {bd}")
    else:
        print("  All package dependencies appear to be resolved.")
    print("-" * 80)

    todos = scan_todos(target_dir)
    print(f"UNFINISHED TASKS & COMMENTS (Found {len(todos):,} items):")
    if not todos:
        print("  None found in source code files.")
    else:
        for path, line, desc in todos[:10]:
            print(f"  - {path}:{line} -> {desc}")
        if len(todos) > 10:
            print(f"  ... and {len(todos) - 10} more items.")
    print("-" * 80)

    print("SUGGESTED NEXT STEPS:")
    step_num = 1
    if broken_deps:
        b_str = " ".join(broken_deps[:3])
        print(f"  {step_num}. Resolve missing dependencies: pip install {b_str}")
        step_num += 1
    if todos:
        t_path = todos[0][0]
        print(f"  {step_num}. Address active code annotations (TODOs in '{t_path}')")
        step_num += 1
    print(
        f"  {step_num}. Verify project execution setups using listed entry endpoints."
    )
    print("========================================================================")


if __name__ == "__main__":
    main()
