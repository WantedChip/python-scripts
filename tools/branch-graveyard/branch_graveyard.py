"""Find local and remote branches that are merged, abandoned, duplicated, or

attached to closed PRs, with a safe interactive cleanup mode.
"""

# pylint: disable=duplicate-code

import argparse
import fnmatch
import json
import logging
import re
import subprocess  # nosec
import sys
import urllib.request
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple


class GitCommandError(Exception):
    """Exception raised when a Git command fails."""


def run_git(args: List[str], cwd: Optional[str] = None) -> str:
    """Run a Git command and return stdout.

    Args:
        args: List of Git arguments (e.g. ['branch', '--merged']).
        cwd: Directory in which to run the command.

    Returns:
        The decoded stdout string of the command.

    Raises:
        GitCommandError: If the command returns a non-zero exit code.
    """
    cmd = ["git"] + args
    logging.debug("Running: %s", " ".join(cmd))
    try:
        result = subprocess.run(  # nosec
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as err:
        logging.error("Git command failed: %s\nStderr: %s", err, err.stderr)
        raise GitCommandError(
            f"Git command failed: {' '.join(cmd)}. Error: {err.stderr.strip()}"
        ) from err


def get_default_branch(repo_path: str) -> str:
    """Detect the default branch of the repository.

    Args:
        repo_path: Path to the git repository.

    Returns:
        The name of the default branch (e.g., 'main' or 'master').
    """
    try:
        # Try checking remote show origin or symbolic-ref refs/remotes/origin/HEAD
        symbolic = run_git(["symbolic-ref", "refs/remotes/origin/HEAD"], cwd=repo_path)
        return symbolic.split("/")[-1]
    except GitCommandError:
        pass

    try:
        # Try local default branch via config or HEAD ref
        ref = run_git(["symbolic-ref", "--short", "HEAD"], cwd=repo_path)
        return ref
    except GitCommandError:
        return "main"


def get_github_repo_info(
    repo_path: str, remote: str = "origin"
) -> Optional[Tuple[str, str]]:
    """Extract GitHub owner and repository name from the remote URL.

    Args:
        repo_path: Path to the git repository.
        remote: Git remote name.

    Returns:
        A tuple of (owner, repo) if it is a GitHub remote, otherwise None.
    """
    try:
        url = run_git(["remote", "get-url", remote], cwd=repo_path)
    except GitCommandError:
        return None

    # Handle formats:
    # https://github.com/owner/repo.git
    # git@github.com:owner/repo.git
    # https://github.com/owner/repo
    pattern = r"github\.com[:/]([^/]+)/([^/.]+)(?:\.git)?"
    match = re.search(pattern, url)
    if match:
        return match.group(1), match.group(2)
    return None


def fetch_closed_prs_via_gh(repo_path: str) -> Set[str]:
    """Fetch closed pull request branch names using the GitHub CLI (gh).

    Args:
        repo_path: Path to the git repository.

    Returns:
        A set of branch names associated with closed/merged PRs.
    """
    try:
        # Check if gh CLI is installed and user is authenticated
        cmd = [
            "gh",
            "pr",
            "list",
            "--state",
            "closed",
            "--limit",
            "300",
            "--json",
            "headRefName",
        ]
        result = subprocess.run(  # nosec
            cmd,
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)
        return {item["headRefName"] for item in data if "headRefName" in item}
    except (
        subprocess.SubprocessError,
        FileNotFoundError,
        json.JSONDecodeError,
        KeyError,
    ):
        return set()


def fetch_closed_prs_via_api(
    owner: str, repo: str, token: Optional[str] = None
) -> Set[str]:
    """Fetch closed pull request branch names via GitHub REST API.

    Args:
        owner: GitHub repository owner.
        repo: GitHub repository name.
        token: Optional GitHub API token.

    Returns:
        A set of branch names associated with closed/merged PRs.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls?state=closed&per_page=100"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "branch-graveyard-script")
    req.add_header("Accept", "application/vnd.github.v3+json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(req, timeout=10) as response:  # nosec
            data = json.loads(response.read().decode("utf-8"))
            return {
                item["head"]["ref"]
                for item in data
                if "head" in item and "ref" in item.get("head", {})
            }
    except Exception as err:  # pylint: disable=broad-except
        logging.warning("Failed to fetch PRs via GitHub API: %s", err)
        return set()


class BranchInfo:  # pylint: disable=too-few-public-methods
    """Stores information about a Git branch."""

    def __init__(
        self,
        name: str,
        is_remote: bool,
        commit_hash: str,
        timestamp: int,
        author: str,
    ) -> None:
        self.name = name
        self.is_remote = is_remote
        self.commit_hash = commit_hash
        self.timestamp = timestamp
        self.author = author
        self.last_commit_date = datetime.fromtimestamp(timestamp, timezone.utc)


def parse_branches(repo_path: str) -> List[BranchInfo]:
    """Get all local and remote branches with commit details.

    Args:
        repo_path: Path to the git repository.

    Returns:
        A list of BranchInfo objects.
    """
    # Format: %(refname) %(objectname) %(committerdate:raw) %(authorname)
    # E.g. refs/heads/main a9348b... 1718000000 +0000 Author Name
    format_str = "%(refname) %(objectname) %(committerdate:raw) %(authorname)"
    output = run_git(["for-each-ref", f"--format={format_str}"], cwd=repo_path)
    branches = []

    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split(" ", 4)
        if len(parts) < 4:
            continue
        refname, commit_hash, raw_time, raw_tz, author = (
            parts[0],
            parts[1],
            parts[2],
            parts[3],
            parts[4],
        )
        _ = raw_tz  # Unused

        try:
            timestamp = int(raw_time)
        except ValueError:
            continue

        if refname.startswith("refs/heads/"):
            prefix_len = len("refs/heads/")
            name = refname[prefix_len:]
            branches.append(BranchInfo(name, False, commit_hash, timestamp, author))
        elif refname.startswith("refs/remotes/"):
            # Skip origin/HEAD or similar
            prefix_len = len("refs/remotes/")
            name = refname[prefix_len:]
            if "/HEAD" in name:
                continue
            branches.append(BranchInfo(name, True, commit_hash, timestamp, author))

    return branches


def get_merged_branches(repo_path: str, main_branch: str) -> Tuple[Set[str], Set[str]]:
    """Get local and remote branches that are merged into the main branch.

    Args:
        repo_path: Path to the git repository.
        main_branch: Main/default branch name.

    Returns:
        A tuple of (local_merged_set, remote_merged_set).
    """
    local_merged = set()
    try:
        output_local = run_git(["branch", "--merged", main_branch], cwd=repo_path)
        for line in output_local.splitlines():
            line = line.strip().lstrip("*").strip()
            if line and line != main_branch:
                local_merged.add(line)
    except GitCommandError:
        pass

    remote_merged = set()
    try:
        output_remote = run_git(
            ["branch", "-r", "--merged", f"origin/{main_branch}"], cwd=repo_path
        )
        for line in output_remote.splitlines():
            line = line.strip()
            if line and not line.startswith("*") and not line.startswith("origin/HEAD"):
                # Remove remote prefix (e.g. 'origin/')
                parts = line.split("/", 1)
                if len(parts) == 2 and parts[1] != main_branch:
                    remote_merged.add(line)
    except GitCommandError:
        pass

    return local_merged, remote_merged


def is_excluded(name: str, exclude_patterns: List[str]) -> bool:
    """Check if branch name matches any exclusion patterns.

    Args:
        name: Branch name.
        exclude_patterns: List of glob patterns.

    Returns:
        True if matched, False otherwise.
    """
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


def delete_local_branch(repo_path: str, branch: str, dry_run: bool) -> bool:
    """Delete a local branch.

    Args:
        repo_path: Path to the git repository.
        branch: Name of the local branch.
        dry_run: If True, only log what would be done.

    Returns:
        True if deleted or dry-run, False on failure.
    """
    if dry_run:
        print(f"[DRY-RUN] Would delete local branch: {branch}")
        return True
    try:
        run_git(["branch", "-d", branch], cwd=repo_path)
        print(f"Deleted local branch: {branch}")
        return True
    except GitCommandError:
        try:
            # Force delete if standard delete fails
            run_git(["branch", "-D", branch], cwd=repo_path)
            print(f"Force deleted local branch: {branch}")
            return True
        except GitCommandError as err:
            print(f"Failed to delete local branch {branch}: {err}")
            return False


def delete_remote_branch(
    repo_path: str, remote: str, branch: str, dry_run: bool
) -> bool:
    """Delete a remote branch.

    Args:
        repo_path: Path to the git repository.
        remote: Name of the remote (e.g. 'origin').
        branch: Name of the branch (excluding remote prefix).
        dry_run: If True, only log what would be done.

    Returns:
        True if deleted or dry-run, False on failure.
    """
    if dry_run:
        print(f"[DRY-RUN] Would delete remote branch: {remote}/{branch}")
        return True
    try:
        run_git(["push", remote, "--delete", branch], cwd=repo_path)
        print(f"Deleted remote branch: {remote}/{branch}")
        return True
    except GitCommandError as err:
        print(f"Failed to delete remote branch {remote}/{branch}: {err}")
        return False


def perform_interactive_cleanup(  # pylint: disable=too-many-branches
    repo_path: str,
    local_to_delete: List[str],
    remote_to_delete: List[Tuple[str, str]],
    dry_run: bool,
) -> None:
    """Prompt user interactively to clean up branches."""
    if local_to_delete:
        print("\n--- Local branches to clean up ---")
        for idx, br in enumerate(local_to_delete):
            print(f"[{idx}] {br}")
        val = (
            input(
                "Enter branch indices to delete (comma-separated, 'all', or 'none'): "
            )
            .strip()
            .lower()
        )
        if val == "all":
            for br in local_to_delete:
                delete_local_branch(repo_path, br, dry_run)
        elif val and val != "none":
            try:
                indices = [int(i.strip()) for i in val.split(",")]
                for idx in indices:
                    if 0 <= idx < len(local_to_delete):
                        delete_local_branch(repo_path, local_to_delete[idx], dry_run)
            except ValueError:
                print("Invalid input.")

    if remote_to_delete:
        print("\n--- Remote branches to clean up ---")
        for idx, (remote, br) in enumerate(remote_to_delete):
            print(f"[{idx}] {remote}/{br}")
        val = (
            input("Enter remote branch indices to delete ('all', 'none', or list): ")
            .strip()
            .lower()
        )
        if val == "all":
            for remote, br in remote_to_delete:
                delete_remote_branch(repo_path, remote, br, dry_run)
        elif val and val != "none":
            try:
                indices = [int(i.strip()) for i in val.split(",")]
                for idx in indices:
                    if 0 <= idx < len(remote_to_delete):
                        r, b = remote_to_delete[idx]
                        delete_remote_branch(repo_path, r, b, dry_run)
            except ValueError:
                print("Invalid input.")


# pylint: disable=too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-locals,too-many-branches
def process_branches(
    branches: List[BranchInfo],
    local_merged: Set[str],
    remote_merged: Set[str],
    closed_pr_branches: Set[str],
    main_branch: str,
    days_threshold: int,
    exclude_patterns: List[str],
) -> Tuple[Dict[str, List[BranchInfo]], Dict[str, Set[str]]]:
    """Process and categorize branches.

    Args:
        branches: List of all BranchInfo.
        local_merged: Set of local merged branches.
        remote_merged: Set of remote merged branches.
        closed_pr_branches: Set of branches with closed PRs.
        main_branch: Name of default branch.
        days_threshold: Threshold for stale branches.
        exclude_patterns: Exclusion glob patterns.

    Returns:
        A tuple of (categorized_branches, duplicates_map).
    """
    categories: Dict[str, List[BranchInfo]] = {
        "merged": [],
        "abandoned": [],
        "duplicated": [],
        "closed_pr": [],
    }

    commit_to_branches: Dict[str, List[BranchInfo]] = {}
    now = datetime.now(timezone.utc)

    for br in branches:
        # Skip main/master branch
        if br.name == main_branch or br.name.endswith(f"/{main_branch}"):
            continue

        if is_excluded(br.name, exclude_patterns):
            continue

        # Duplicates check preparation
        commit_to_branches.setdefault(br.commit_hash, []).append(br)

        # 1. Merged
        is_merged = False
        if not br.is_remote and br.name in local_merged:
            is_merged = True
        elif br.is_remote and br.name in remote_merged:
            is_merged = True

        if is_merged:
            categories["merged"].append(br)
            continue

        # 2. Closed PR
        # For remote branch, strip remote prefix like 'origin/'
        clean_name = br.name.split("/", 1)[1] if br.is_remote else br.name
        if clean_name in closed_pr_branches:
            categories["closed_pr"].append(br)
            continue

        # 3. Abandoned / Stale
        age = now - br.last_commit_date
        if age.days > days_threshold:
            categories["abandoned"].append(br)

    # 4. Duplicated (pointing to same commit)
    for _, br_list in commit_to_branches.items():
        if len(br_list) > 1:
            # Check if any branches are not ignored/excluded and are duplicates
            for br in br_list:
                # We skip main/master here as it is not a candidate duplicate to delete
                if br.name != main_branch and not br.name.endswith(f"/{main_branch}"):
                    if not is_excluded(br.name, exclude_patterns):
                        categories["duplicated"].append(br)

    return categories, {
        c: {b.name for b in br_list}
        for c, br_list in commit_to_branches.items()
        if len(br_list) > 1
    }


def main() -> (
    None
):  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    """Main execution entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Find local and remote branches that are merged, "
            "abandoned, duplicated, or attached to closed PRs."
        )
    )
    parser.add_argument(
        "repo_path",
        nargs="?",
        default=".",
        help="Path to target git repository (default: current directory).",
    )
    parser.add_argument(
        "-d",
        "--days",
        type=int,
        default=30,
        help="Days threshold to consider a branch abandoned (default: 30).",
    )
    parser.add_argument(
        "-m",
        "--main",
        help="Main/default branch (e.g. main, master). Auto-detected if not specified.",
    )
    parser.add_argument(
        "-r",
        "--remote",
        default="origin",
        help="Git remote name (default: origin).",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Interactively delete selected graveyard branches.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run; show what would be deleted without deleting.",
    )
    parser.add_argument(
        "--github-token",
        help="GitHub Personal Access Token to check closed PRs via GitHub API.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Glob pattern of branches to exclude (can be specified multiple times).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output.",
    )

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    repo_path = args.repo_path
    main_branch = args.main or get_default_branch(repo_path)
    print(f"Analyzing repository: {repo_path}")
    print(f"Default branch: {main_branch}")

    try:
        branches = parse_branches(repo_path)
    except GitCommandError as err:
        print(f"Error parsing branches: {err}")
        sys.exit(1)

    local_merged, remote_merged = get_merged_branches(repo_path, main_branch)

    # Fetch closed PR branches
    closed_pr_branches = set()
    owner_repo = get_github_repo_info(repo_path, args.remote)
    if owner_repo:
        owner, repo = owner_repo
        print(f"Detected GitHub repository: {owner}/{repo}")
        if args.github_token:
            print("Fetching closed PRs via GitHub REST API...")
            closed_pr_branches = fetch_closed_prs_via_api(
                owner, repo, args.github_token
            )
        else:
            print("Attempting to fetch closed PRs via gh CLI...")
            closed_pr_branches = fetch_closed_prs_via_gh(repo_path)
    else:
        logging.warning("Could not detect GitHub repository remote URL.")

    exclude_patterns = args.exclude
    categories, dup_map = process_branches(
        branches,
        local_merged,
        remote_merged,
        closed_pr_branches,
        main_branch,
        args.days,
        exclude_patterns,
    )

    # Print results
    local_to_delete: List[str] = []
    remote_to_delete: List[Tuple[str, str]] = []

    for cat, list_br in categories.items():
        if not list_br:
            continue
        print(f"\n[{cat.upper()}] Branches:")
        # Deduplicate multiple outputs in case a branch matches multiple categories
        seen = set()
        for br in list_br:
            type_str = "remote" if br.is_remote else "local"
            last_date = br.last_commit_date.strftime("%Y-%m-%d")
            info = (
                f"  - {br.name} ({type_str}) | Commit: {br.commit_hash[:8]} | "
                f"Last update: {last_date} by {br.author}"
            )
            if br.name in seen:
                continue
            seen.add(br.name)
            print(info)

            if cat in ("merged", "closed_pr", "abandoned"):
                if br.is_remote:
                    # Strip remote name (e.g. 'origin/feat' -> ('origin', 'feat'))
                    parts = br.name.split("/", 1)
                    if len(parts) == 2:
                        remote_to_delete.append((parts[0], parts[1]))
                else:
                    local_to_delete.append(br.name)

    if dup_map:
        print("\n[DUPLICATED] Commits shared by multiple branches:")
        for commit, br_names in dup_map.items():
            print(f"  - Commit {commit[:8]} is pointed to by: {', '.join(br_names)}")

    if args.interactive:
        # Deduplicate delete lists
        local_to_delete = sorted(list(set(local_to_delete)))
        # Deduplicate remote deletes
        remote_to_delete = sorted(list(set(remote_to_delete)))
        perform_interactive_cleanup(
            repo_path, local_to_delete, remote_to_delete, args.dry_run
        )
    else:
        print("\nRun with -i/--interactive to clean up graveyard branches.")


if __name__ == "__main__":
    main()
