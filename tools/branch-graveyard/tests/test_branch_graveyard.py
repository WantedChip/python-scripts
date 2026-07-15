"""Tests for branch-graveyard script."""

# pylint: disable=duplicate-code,wrong-import-position,line-too-long,import-error

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from branch_graveyard import (  # noqa: E402
    BranchInfo,
    GitCommandError,
    delete_local_branch,
    delete_remote_branch,
    fetch_closed_prs_via_api,
    fetch_closed_prs_via_gh,
    get_default_branch,
    get_github_repo_info,
    get_merged_branches,
    is_excluded,
    main,
    parse_branches,
    process_branches,
    run_git,
)


def test_is_excluded() -> None:
    """Test is_excluded function."""
    assert is_excluded("feature/abc", ["feature/*"])
    assert not is_excluded("main", ["feature/*"])
    assert is_excluded("dev", ["dev", "prod"])


@patch("subprocess.run")
def test_run_git_success(mock_run: MagicMock) -> None:
    """Test running a Git command successfully."""
    mock_run.return_value = MagicMock(
        returncode=0, stdout="  refs/heads/main  \n", stderr=""
    )
    res = run_git(["branch"])
    assert res == "refs/heads/main"
    mock_run.assert_called_once_with(
        ["git", "branch"],
        cwd=None,
        stdout=-1,
        stderr=-1,
        text=True,
        check=True,
    )


@patch("subprocess.run")
def test_run_git_failure(mock_run: MagicMock) -> None:
    """Test run_git handles errors."""
    import subprocess

    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1, cmd=["git", "branch"], stderr="Fatal error"
    )
    with pytest.raises(GitCommandError) as excinfo:
        run_git(["branch"])
    assert "Fatal error" in str(excinfo.value)


@patch("branch_graveyard.run_git")
def test_get_default_branch(mock_run_git: MagicMock) -> None:
    """Test get_default_branch functionality."""
    # Scenario 1: remote origin HEAD is set
    mock_run_git.return_value = "refs/remotes/origin/main"
    assert get_default_branch(".") == "main"

    # Scenario 2: remote HEAD fails, fallback to local HEAD symbolic ref
    mock_run_git.side_effect = [GitCommandError("fail"), "master"]
    assert get_default_branch(".") == "master"

    # Scenario 3: all fail, default to 'main'
    mock_run_git.side_effect = GitCommandError("fail")
    assert get_default_branch(".") == "main"


@patch("branch_graveyard.run_git")
def test_get_github_repo_info(mock_run_git: MagicMock) -> None:
    """Test get_github_repo_info with different URL formats."""
    # HTTPS
    mock_run_git.return_value = "https://github.com/owner/repo.git"
    assert get_github_repo_info(".") == ("owner", "repo")

    # SSH
    mock_run_git.return_value = "git@github.com:owner2/repo2.git"
    assert get_github_repo_info(".") == ("owner2", "repo2")

    # SSH without .git
    mock_run_git.return_value = "git@github.com:owner3/repo3"
    assert get_github_repo_info(".") == ("owner3", "repo3")

    # Fail
    mock_run_git.side_effect = GitCommandError("error")
    assert get_github_repo_info(".") is None


@patch("subprocess.run")
def test_fetch_closed_prs_via_gh(mock_run: MagicMock) -> None:
    """Test fetch_closed_prs_via_gh mock response."""
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps([{"headRefName": "feat-1"}, {"headRefName": "feat-2"}]),
        stderr="",
    )
    res = fetch_closed_prs_via_gh(".")
    assert res == {"feat-1", "feat-2"}

    # Subprocess fails
    mock_run.side_effect = FileNotFoundError()
    assert fetch_closed_prs_via_gh(".") == set()


@patch("urllib.request.urlopen")
def test_fetch_closed_prs_via_api(mock_urlopen: MagicMock) -> None:
    """Test fetch_closed_prs_via_api mock response."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(
        [
            {"head": {"ref": "api-feat-1"}},
            {"head": {"ref": "api-feat-2"}},
        ]
    ).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    res = fetch_closed_prs_via_api("owner", "repo", "token")
    assert res == {"api-feat-1", "api-feat-2"}

    # Request errors out
    mock_urlopen.side_effect = Exception("network error")
    assert fetch_closed_prs_via_api("owner", "repo") == set()


@patch("branch_graveyard.run_git")
def test_parse_branches(mock_run_git: MagicMock) -> None:
    """Test parsing branches output from git for-each-ref."""
    output = (
        "refs/heads/main hash1 1718000000 +0000 Author A\n"
        "refs/heads/feature/test hash2 1719000000 +0000 Author B\n"
        "refs/remotes/origin/main hash1 1718000000 +0000 Author A\n"
        "refs/remotes/origin/HEAD hash1 1718000000 +0000 Author A\n"
        "refs/remotes/origin/feature/remote hash3 1720000000 +0000 Author C\n"
    )
    mock_run_git.return_value = output
    res = parse_branches(".")
    assert len(res) == 4
    # Local branch
    assert res[0].name == "main"
    assert not res[0].is_remote
    assert res[0].commit_hash == "hash1"
    assert res[0].timestamp == 1718000000
    assert res[0].author == "Author A"

    # Remote branch (origin/HEAD should be skipped)
    assert res[3].name == "origin/feature/remote"
    assert res[3].is_remote
    assert res[3].commit_hash == "hash3"


@patch("branch_graveyard.run_git")
def test_get_merged_branches(mock_run_git: MagicMock) -> None:
    """Test get_merged_branches for local and remote."""
    mock_run_git.side_effect = [
        "  * main\n  feature/merged\n",  # local merged
        (
            "  origin/main\n"
            "  origin/remote-merged\n"
            "  origin/HEAD -> origin/main\n"
        ),  # remote merged
    ]
    local, remote = get_merged_branches(".", "main")
    assert local == {"feature/merged"}
    assert remote == {"origin/remote-merged"}


@patch("branch_graveyard.run_git")
def test_delete_local_branch(mock_run_git: MagicMock) -> None:
    """Test local branch deletion."""
    # Dry run
    assert delete_local_branch(".", "feature", True)
    mock_run_git.assert_not_called()

    # Success normal delete
    mock_run_git.return_value = ""
    assert delete_local_branch(".", "feature", False)
    mock_run_git.assert_called_with(["branch", "-d", "feature"], cwd=".")

    # Fallback to force delete
    mock_run_git.side_effect = [GitCommandError("error"), ""]
    assert delete_local_branch(".", "feature-force", False)

    # All fail
    mock_run_git.side_effect = GitCommandError("error")
    assert not delete_local_branch(".", "feature-fail", False)


@patch("branch_graveyard.run_git")
def test_delete_remote_branch(mock_run_git: MagicMock) -> None:
    """Test remote branch deletion."""
    # Dry run
    assert delete_remote_branch(".", "origin", "feature", True)
    mock_run_git.assert_not_called()

    # Success
    mock_run_git.return_value = ""
    assert delete_remote_branch(".", "origin", "feature", False)
    mock_run_git.assert_called_with(["push", "origin", "--delete", "feature"], cwd=".")

    # Failure
    mock_run_git.side_effect = GitCommandError("error")
    assert not delete_remote_branch(".", "origin", "feature-fail", False)


def test_process_branches() -> None:
    """Test branch categorization logic."""
    branches = [
        # Merged local branch
        BranchInfo("feature/merged", False, "hash_merged", 1718000000, "Author A"),
        # Merged remote branch
        BranchInfo(
            "origin/feature/rmerged", True, "hash_rmerged", 1718000000, "Author A"
        ),
        # Stale local branch
        BranchInfo("feature/stale", False, "hash_stale", 1000000000, "Author B"),
        # Closed PR local branch
        BranchInfo("feature/closed-pr", False, "hash_closed", 1719000000, "Author C"),
        # Duplicate branch pointing to hash_merged
        BranchInfo("feature/dup1", False, "hash_dup", 1719000000, "Author D"),
        BranchInfo("feature/dup2", False, "hash_dup", 1719000000, "Author E"),
    ]

    local_merged = {"feature/merged"}
    remote_merged = {"origin/feature/rmerged"}
    closed_pr_branches = {"feature/closed-pr"}

    # Target date logic uses now (e.g. 2026).
    # 1719000000 is ~2024, so it will be abandoned if not merged/closed.
    # To test accurately, let's mock processing.
    categories, dup_map = process_branches(
        branches=branches,
        local_merged=local_merged,
        remote_merged=remote_merged,
        closed_pr_branches=closed_pr_branches,
        main_branch="main",
        days_threshold=10,  # very small threshold
        exclude_patterns=[],
    )

    assert any(b.name == "feature/merged" for b in categories["merged"])
    assert any(b.name == "origin/feature/rmerged" for b in categories["merged"])
    assert any(b.name == "feature/closed-pr" for b in categories["closed_pr"])
    assert any(b.name == "feature/stale" for b in categories["abandoned"])
    assert len(dup_map["hash_dup"]) == 2


@patch("branch_graveyard.perform_interactive_cleanup")
@patch("branch_graveyard.fetch_closed_prs_via_gh")
@patch("branch_graveyard.get_merged_branches")
@patch("branch_graveyard.parse_branches")
@patch("branch_graveyard.get_github_repo_info")
@patch("branch_graveyard.get_default_branch")
@patch("sys.argv")
def test_main_cli(
    mock_argv: MagicMock,
    mock_default_branch: MagicMock,
    mock_repo_info: MagicMock,
    mock_parse: MagicMock,
    mock_merged: MagicMock,
    mock_gh_prs: MagicMock,
    mock_interactive: MagicMock,
) -> None:
    """Test the CLI entry point integration."""
    mock_argv.__getitem__.side_effect = lambda x: ["branch_graveyard.py", "-i"][x]
    mock_argv.__len__.return_value = 2

    mock_default_branch.return_value = "main"
    mock_repo_info.return_value = ("owner", "repo")
    mock_parse.return_value = [
        BranchInfo("feature/merged", False, "hash1", 1718000000, "Author A"),
    ]
    mock_merged.return_value = ({"feature/merged"}, set())
    mock_gh_prs.return_value = set()

    main()
    mock_interactive.assert_called_once()


@patch("branch_graveyard.delete_remote_branch")
@patch("branch_graveyard.delete_local_branch")
@patch("builtins.input")
def test_perform_interactive_cleanup(
    mock_input: MagicMock,
    mock_del_local: MagicMock,
    mock_del_remote: MagicMock,
) -> None:
    """Test interactive cleanup flows."""
    from branch_graveyard import perform_interactive_cleanup

    # Test 'all' option
    mock_input.side_effect = ["all", "all"]
    perform_interactive_cleanup(".", ["loc1", "loc2"], [("origin", "rem1")], False)
    assert mock_del_local.call_count == 2
    assert mock_del_remote.call_count == 1

    mock_del_local.reset_mock()
    mock_del_remote.reset_mock()

    # Test specific indices
    mock_input.side_effect = ["0", "0"]
    perform_interactive_cleanup(".", ["loc1", "loc2"], [("origin", "rem1")], False)
    mock_del_local.assert_called_once_with(".", "loc1", False)
    mock_del_remote.assert_called_once_with(".", "origin", "rem1", False)

    mock_del_local.reset_mock()
    mock_del_remote.reset_mock()

    # Test 'none' option
    mock_input.side_effect = ["none", "none"]
    perform_interactive_cleanup(".", ["loc1"], [("origin", "rem1")], False)
    mock_del_local.assert_not_called()
    mock_del_remote.assert_not_called()

    # Test invalid index
    mock_input.side_effect = ["invalid", "99"]
    perform_interactive_cleanup(".", ["loc1"], [("origin", "rem1")], False)
    mock_del_local.assert_not_called()
    mock_del_remote.assert_not_called()
