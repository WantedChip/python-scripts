#!/usr/bin/env python3
"""Git Undo Explain.

Explains the safest Git commands to recover from common mistakes, illustrates
the visual before-and-after state changes, and optionally executes commands.
"""

import argparse
import os
import subprocess  # nosec B404
import sys
from typing import Sequence


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


SCENARIOS = {
    1: {
        "title": (
            "I committed directly to the wrong branch (e.g. main/master "
            "instead of feature branch)."
        ),
        "explanation": (
            "This will move your new commits to a feature branch, then reset "
            "the active branch back to its origin tracking state."
        ),
        "commands": [
            "git branch temporary-branch-backup",
            "git reset --hard HEAD~1",
            "git checkout temporary-branch-backup",
        ],
        "visual": """
[BEFORE]
    origin/main: A --- B
    local main:  A --- B --- C (Wrong Commit!)

[AFTER]
    local main:  A --- B
    temp-branch: A --- B --- C (Saved feature commit!)
""",
    },
    2: {
        "title": "I need to undo my last commit (keep my modifications local).",
        "explanation": (
            "This will undo the commit record but leave all modified files "
            "intact in your working directory."
        ),
        "commands": ["git reset --soft HEAD~1"],
        "visual": """
[BEFORE]
    Commits history:  Commit A -> Commit B (Last Commit)
    Working directory: Clean

[AFTER]
    Commits history:  Commit A
    Working directory: Modified files from Commit B are unstaged
""",
    },
    3: {
        "title": ("I need to undo my last commit (discard all changes permanently)."),
        "explanation": (
            "WARNING: This deletes the last commit and discards all "
            "modifications. This action is destructive."
        ),
        "commands": ["git reset --hard HEAD~1"],
        "visual": """
[BEFORE]
    Commits history:  Commit A -> Commit B (Last Commit)
    Working directory: Clean

[AFTER]
    Commits history:  Commit A
    Working directory: Completely clean (Commit B modifications deleted)
""",
    },
    4: {
        "title": "I accidentally ran a git reset --hard and lost my commits.",
        "explanation": (
            "We can recover lost commits by finding their references inside "
            "the Git reflog."
        ),
        "commands": [
            "git reflog",
            "# Find your lost commit SHA1 (e.g. 1a2b3c4)",
            "# Run: git reset --hard 1a2b3c4",
        ],
        "visual": """
[BEFORE]
    HEAD -> Commit A (Accidental reset point)
    (Commit B is dangling in Git database)

[AFTER]
    HEAD -> Commit B (Restored using reflog address pointer)
""",
    },
    5: {
        "title": (
            "I committed a file that should have been ignored (e.g. logs/secrets)."
        ),
        "explanation": (
            "This removes the file from Git index tracking without deleting "
            "the file from your local disk."
        ),
        "commands": [
            "git rm --cached <FILE_PATH>",
            "# Append file path to your .gitignore",
        ],
        "visual": """
[BEFORE]
    Git repo tracks:  secret.env (staged or committed)

[AFTER]
    secret.env removed from index tracker (untracked locally)
""",
    },
}


def execute_recovery(commands: Sequence[str], repo_path: str) -> None:
    """Execute the recovery commands in sequence in the target git repository."""
    print(f"\nExecuting recovery commands in: {repo_path}")
    for cmd in commands:
        if cmd.startswith("#"):
            print(f"Skipping guidance instructions: {cmd}")
            continue

        print(f"Running: {cmd}")
        res = subprocess.run(
            cmd,
            shell=True,
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )  # nosec B602
        print(res.stdout.strip())
        if res.stderr.strip():
            print(res.stderr.strip(), file=sys.stderr)

        if res.returncode != 0:
            print(
                "[-] Error: Recovery command sequence failed. Aborting further steps.",
                file=sys.stderr,
            )
            break


# pylint: disable=too-many-statements
def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Safely recover from Git mistakes using guided explanations and "
            "visual cues."
        )
    )
    parser.add_argument(
        "repo_path",
        nargs="?",
        default=".",
        help="Git repository path to recover (default: current directory).",
    )
    parser.add_argument(
        "-s",
        "--scenario",
        type=int,
        choices=[1, 2, 3, 4, 5],
        help="Directly specify recovery scenario ID (1-5).",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Automatically execute recovery commands without asking confirmation.",
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
    print("GIT UNDO EXPLAINER: RECOVERY GUIDE")
    print("========================================================================")

    scenario_id = args.scenario
    if scenario_id is None:
        print("Select a recovery scenario number from the menu below:")
        for idx, details in SCENARIOS.items():
            print(f"  {idx}. {details['title']}")
        print("-" * 80)
        try:
            choice_str = input("Enter choice (1-5): ").strip()
            scenario_id = int(choice_str)
        except (ValueError, KeyboardInterrupt):
            print("\nOperation aborted.")
            sys.exit(0)

    if scenario_id not in SCENARIOS:
        print("Error: Invalid choice.", file=sys.stderr)
        sys.exit(1)

    selected = SCENARIOS[scenario_id]

    print("\n" + "=" * 80)
    print(f"SCENARIO: {selected['title']}")
    print("=" * 80)
    print(f"Explanation: {selected['explanation']}")
    print("\nVisual State Representation:")
    print(selected["visual"])
    print("Recovery Commands:")
    for cmd in selected["commands"]:
        print(f"  $ {cmd}")
    print("=" * 80)

    if not args.yes:
        confirm = (
            input("\nDo you want to execute these recovery commands now? [y/N]: ")
            .strip()
            .lower()
        )
        if confirm not in ("y", "yes"):
            print("Operation aborted. Commands were not executed.")
            sys.exit(0)

    if scenario_id == 5:
        file_path = input("Enter the file path to stop tracking: ").strip()
        if not file_path:
            print("Error: No file path provided.", file=sys.stderr)
            sys.exit(1)
        cmds = [f"git rm --cached {file_path}", f"echo {file_path} >> .gitignore"]
        execute_recovery(cmds, repo_path)
    else:
        execute_recovery(selected["commands"], repo_path)


if __name__ == "__main__":
    main()
