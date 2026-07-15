"""Commit Splitter.

Analyzes the Git working tree (staged, unstaged, untracked changes)
and suggests logical groups of files to split into separate commits.
"""

import argparse
import json
import subprocess  # nosec B404
import sys
from typing import Dict, List, Tuple


def run_git(args: List[str]) -> str:
    """Runs a git command and returns its standard output.

    Args:
        args: Git subcommand and parameters list.

    Returns:
        Standard output string of the command.

    Raises:
        RuntimeError: If Git command fails or is not found.
    """
    try:
        # pylint: disable=subprocess-run-check
        res = subprocess.run(  # nosec B603
            ["git"] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if res.returncode != 0:
            raise RuntimeError(res.stderr.strip())
        return res.stdout
    except (FileNotFoundError, OSError) as err:
        raise RuntimeError(f"Git command execution failed: {err}") from err


def get_git_status() -> List[Tuple[str, str]]:
    """Retrieves unstaged, staged, and untracked files from Git porcelain status.

    Returns:
        List of tuples matching (status_code, file_path).
    """
    try:
        output = run_git(["status", "--porcelain"])
    except RuntimeError as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)

    changes = []
    for line in output.splitlines():
        if len(line) > 3:
            status = line[:2]
            path = line[3:].strip()
            # Handle renames e.g. "R  old -> new"
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            # Strip quotes if present
            if path.startswith('"') and path.endswith('"'):
                path = path[1:-1]
            changes.append((status, path))
    return changes


# pylint: disable=too-many-return-statements
def get_component_name(path: str) -> str:
    """Heuristically extracts a logical component name from a file path.

    Args:
        path: Relative file path in the repository.

    Returns:
        Name of the component, or 'global' for root files.
    """
    parts = path.replace("\\", "/").split("/")
    if len(parts) <= 1:
        return "global"

    # Monorepo structure category/script-name/
    category = parts[0]
    if category in ("tools", "checkers", "automation", "converters", "scraping"):
        return parts[1]

    # Handle standard source/tests layout
    if parts[0] in ("src", "tests", "test"):
        if len(parts) > 1:
            name = parts[1]
            if name.startswith("test_"):
                name = name[5:]
            if name.endswith(".py"):
                name = name[:-3]
            return name

    return parts[0]


def suggest_commit_message(component: str, paths: List[str]) -> str:
    """Generates a standard git commit message based on modified files.

    Args:
        component: The logical component name.
        paths: List of file paths modified in the commit.

    Returns:
        Proposed commit message string.
    """
    if component == "global":
        if any(
            p.endswith("requirements-dev.txt") or p.endswith("pyproject.toml")
            for p in paths
        ):
            return "chore: update development dependencies and tools configuration"
        if any(p.endswith("README.md") or p.endswith("INDEX.md") for p in paths):
            return "docs: update repository documentation indexes"
        return "chore: update repository infrastructure files"

    # Analyze file extensions
    is_test = all("test" in p.lower() for p in paths)
    is_docs = all(p.lower().endswith((".md", ".txt")) for p in paths)
    is_code = any(p.endswith(".py") for p in paths)

    if is_test:
        return f"test({component}): add unit tests covering changes"
    if is_docs:
        return f"docs({component}): update documentation notes"
    if is_code:
        # Check if there are any new untracked files
        return f"feat({component}): implement core features and improvements"
    return f"refactor({component}): update assets and resources"


def group_changes(changes: List[Tuple[str, str]]) -> Dict[str, List[str]]:
    """Groups file changes logically based on directory structure and component names.

    Args:
        changes: List of status code and path tuples.

    Returns:
        Dictionary mapping component names to lists of file paths.
    """
    groups: Dict[str, List[str]] = {}

    for _, path in changes:
        comp = get_component_name(path)
        if comp not in groups:
            groups[comp] = []
        groups[comp].append(path)

    # Secondary pairing: merge orphan test folders or files into component groups
    # if there are matching base names
    for comp in list(groups.keys()):
        if comp.startswith("test_") or comp == "tests":
            # Try to resolve to a source component
            base = comp[5:] if comp.startswith("test_") else ""
            if base in groups:
                groups[base].extend(groups[comp])
                del groups[comp]

    return groups


def print_suggestions(groups: Dict[str, List[str]], format_json: bool) -> None:
    """Outputs the suggested commit groups to console.

    Args:
        groups: Dictionary mapping component to files.
        format_json: If True, formats output as JSON instead of human-readable text.
    """
    suggestions = []
    for comp, files in sorted(groups.items()):
        suggestions.append(
            {
                "component": comp,
                "message": suggest_commit_message(comp, files),
                "files": sorted(files),
            }
        )

    if format_json:
        print(json.dumps(suggestions, indent=2))
        return

    if not suggestions:
        print("No changes detected in working tree.")
        return

    print("=== Suggested Commit Groups ===")
    for idx, sug in enumerate(suggestions, 1):
        print(f"\n[{idx}] Component: {sug['component']}")
        print(f"    Suggested Message: {sug['message']}")
        print("    Files:")
        for file in sug["files"]:
            print(f"      - {file}")


def apply_commits(groups: Dict[str, List[str]], interactive: bool) -> None:
    """Stages and commits file groups sequentially.

    Args:
        groups: Component mapping dictionary.
        interactive: If True, prompts the user for confirmation on each commit.
    """
    # pylint: disable=too-many-branches
    print("Applying split commits...")
    for comp, files in sorted(groups.items()):
        msg = suggest_commit_message(comp, files)

        print(f"\nGroup: {comp}")
        print("Files:")
        for file in files:
            print(f"  - {file}")
        print(f"Proposed message: {msg}")

        if interactive:
            prompt = "Commit this group? [y(es) / n(o) / e(dit message) / q(uit)]: "
            resp = input(prompt).strip().lower()
            if resp == "q":
                print("Aborting remaining commits.")
                break
            if resp in ("n", ""):
                print("Skipping group.")
                continue
            if resp == "e":
                custom_msg = input("Enter custom commit message: ").strip()
                if custom_msg:
                    msg = custom_msg

        # Add files to stage
        print("Staging files...")
        try:
            # Stage files
            run_git(["add"] + files)
            # Create commit
            print(f"Creating commit: '{msg}'")
            run_git(["commit", "-m", msg])
        except RuntimeError as err:
            print(f"Warning: Failed to commit group {comp}: {err}", file=sys.stderr)
            # Unstage files to leave clean
            try:
                run_git(["reset", "HEAD"] + files)
            except RuntimeError:
                pass


def main() -> None:
    """CLI entry point for commit-splitter."""
    # pylint: disable=duplicate-code
    parser = argparse.ArgumentParser(
        description="Analyze a messy working tree and suggest logical commits."
    )
    parser.add_argument(
        "-a",
        "--apply",
        action="store_true",
        help="Stage and commit suggested groups sequentially (non-interactive).",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Stage and commit interactively, prompting for each group.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output suggestions as structured JSON.",
    )

    args = parser.parse_args()

    changes = get_git_status()
    groups = group_changes(changes)

    if args.apply or args.interactive:
        apply_commits(groups, args.interactive)
    else:
        print_suggestions(groups, args.json)


if __name__ == "__main__":
    main()
