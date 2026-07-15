"""Tests for repo-size-history script."""

# pylint: disable=duplicate-code,wrong-import-position,line-too-long,import-error

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from repo_size_history import (  # noqa: E402
    GitCommandError,
    analyze_history,
    format_size,
    get_commit_list,
    get_repo_files,
    main,
    run_git,
)


@patch("subprocess.run")
def test_run_git_success(mock_run: MagicMock) -> None:
    """Test successful run_git command execution."""
    mock_run.return_value = MagicMock(returncode=0, stdout="git output\n", stderr="")
    res = run_git(["status"])
    assert res == "git output"


@patch("subprocess.run")
def test_run_git_failure(mock_run: MagicMock) -> None:
    """Test run_git exception propagation."""
    import subprocess

    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=128, cmd=["git", "status"], stderr="fatal: error"
    )
    with pytest.raises(GitCommandError) as excinfo:
        run_git(["status"])
    assert "fatal: error" in str(excinfo.value)


@patch("repo_size_history.run_git")
def test_get_commit_list(mock_run_git: MagicMock) -> None:
    """Test fetching and parsing commit list."""
    mock_run_git.return_value = (
        "hash2|1719000000|Author B|Commit 2\nhash1|1718000000|Author A|Commit 1"
    )
    commits = get_commit_list(".", 10)
    assert len(commits) == 2
    # Chronological ordering check:
    # oldest first (timestamp 1718000000 should be index 0)
    assert commits[0][0] == "hash1"
    assert commits[1][0] == "hash2"

    # Tags only configuration
    commits_tags = get_commit_list(".", 10, tags_only=True)
    assert len(commits_tags) == 2


@patch("repo_size_history.run_git")
def test_get_commit_list_error(mock_run_git: MagicMock) -> None:
    """Test get_commit_list handling log errors."""
    mock_run_git.side_effect = GitCommandError("error log")
    with pytest.raises(SystemExit) as excinfo:
        get_commit_list(".", 10)
    assert excinfo.value.code == 1


@patch("repo_size_history.run_git")
def test_get_repo_files(mock_run_git: MagicMock) -> None:
    """Test parsing repo files output from ls-tree."""
    output = (
        "100644 blob hash_blob1     1000\tfile1.txt\n"
        "100644 blob hash_blob2     5000000\tfile2.txt\n"
        "040000 tree hash_tree         -\tsubdir\n"
    )
    mock_run_git.return_value = output
    files = get_repo_files(".", "HEAD")
    assert len(files) == 2
    assert files["file1.txt"] == 1000
    assert files["file2.txt"] == 5000000

    # Failure scenario (e.g. empty commit or command error)
    mock_run_git.side_effect = GitCommandError("error ls-tree")
    assert get_repo_files(".", "HEAD") == {}


def test_format_size() -> None:
    """Test formatting helper."""
    assert format_size(100) == "100.00 B"
    assert format_size(1500) == "1.46 KB"
    assert format_size(1024 * 1024 * 3) == "3.00 MB"


@patch("repo_size_history.get_repo_files")
@patch("builtins.print")
def test_analyze_history(mock_print: MagicMock, mock_get_files: MagicMock) -> None:
    """Test walking history, detecting spikes and warning on large files."""
    commits = [
        ("hash1", 1718000000, "Author A", "Initial commit"),
        ("hash2", 1719000000, "Author B", "Add heavy file"),
    ]

    mock_get_files.side_effect = [
        {"file1.txt": 1000},  # files in hash1
        {
            "file1.txt": 1000,
            "heavy.bin": 6000000,
        },  # files in hash2 (growth is ~6MB, >10%)
    ]

    # Threshold: 10% spike, warning for file >5MB (5.0)
    analyze_history(".", commits, 10.0, 5.0)
    # Check that Warning/Spike detected print statements were triggered
    mock_print.assert_any_call("  * Warning/Spike detected at commit hash2!")
    mock_print.assert_any_call("    - Heavy files added or expanded in this commit:")


@patch("repo_size_history.get_commit_list")
@patch("repo_size_history.analyze_history")
@patch("builtins.print")
@patch("os.path.exists")
@patch("sys.argv")
def test_main_cli(
    mock_argv: MagicMock,
    mock_exists: MagicMock,
    mock_print: MagicMock,
    mock_analyze: MagicMock,
    mock_get_commits: MagicMock,
) -> None:
    """Test main entry point parsing."""
    mock_argv.__getitem__.side_effect = lambda x: ["repo_size_history.py", "."][x]
    mock_argv.__len__.return_value = 2
    mock_exists.return_value = True

    # Scenario 1: valid commits
    mock_get_commits.return_value = [("hash1", 1718000000, "Author A", "Msg")]
    main()
    mock_analyze.assert_called_once()

    # Scenario 2: no commits
    mock_analyze.reset_mock()
    mock_get_commits.return_value = []
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 0
    mock_print.assert_any_call("No commits found matching the criteria.")

    # Scenario 3: not a git repo
    mock_exists.return_value = False
    with pytest.raises(SystemExit) as excinfo_repo:
        main()
    assert excinfo_repo.value.code == 1
