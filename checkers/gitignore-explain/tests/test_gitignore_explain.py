"""Tests for gitignore-explain script."""

# pylint: disable=duplicate-code,wrong-import-position,line-too-long,import-error

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gitignore_explain import (  # noqa: E402
    check_tracked,
    explain_ignore,
    get_git_root,
    is_git_repo,
    main,
    run_git,
)


@patch("subprocess.run")
def test_run_git(mock_run: MagicMock) -> None:
    """Test running a Git command via subprocess."""
    mock_run.return_value = MagicMock(returncode=0, stdout="test-out", stderr="")
    code, out, err = run_git(["status"])
    assert code == 0
    assert out == "test-out"
    assert err == ""

    # Exception flow
    import subprocess

    mock_run.side_effect = subprocess.SubprocessError("error")
    code, _, err = run_git(["status"])
    assert code == -1
    assert "error" in err


@patch("gitignore_explain.run_git")
def test_is_git_repo(mock_run_git: MagicMock) -> None:
    """Test is_git_repo detection."""
    mock_run_git.return_value = (0, "true", "")
    assert is_git_repo(".")

    mock_run_git.return_value = (128, "", "fatal: not a git repository")
    assert not is_git_repo(".")


@patch("gitignore_explain.run_git")
def test_get_git_root(mock_run_git: MagicMock) -> None:
    """Test getting git top-level directory."""
    mock_run_git.return_value = (0, "/workspace/root", "")
    assert get_git_root(".") == os.path.abspath("/workspace/root")

    mock_run_git.return_value = (1, "", "error")
    assert get_git_root(".") is None


@patch("gitignore_explain.run_git")
def test_check_tracked(mock_run_git: MagicMock) -> None:
    """Test check_tracked logic."""
    mock_run_git.return_value = (0, "file.txt", "")
    assert check_tracked(".", "file.txt")

    mock_run_git.return_value = (1, "", "fatal: pathspec did not match")
    assert not check_tracked(".", "file.txt")


@patch("gitignore_explain.is_git_repo")
@patch("builtins.print")
def test_explain_ignore_not_repo(
    mock_print: MagicMock, mock_is_repo: MagicMock
) -> None:
    """Test explain_ignore when path is not a git repo."""
    mock_is_repo.return_value = False
    with pytest.raises(SystemExit) as excinfo:
        explain_ignore(".", "file.txt")
    assert excinfo.value.code == 1
    mock_print.assert_any_call("Error: '.' is not a Git repository.")


@patch("gitignore_explain.check_tracked")
@patch("gitignore_explain.is_git_repo")
@patch("builtins.print")
def test_explain_ignore_tracked(
    mock_print: MagicMock, mock_is_repo: MagicMock, mock_tracked: MagicMock
) -> None:
    """Test explain_ignore when path is tracked."""
    mock_is_repo.return_value = True
    mock_tracked.return_value = True

    explain_ignore(".", "file.txt")
    mock_print.assert_any_call(
        "Status: NOT IGNORED (File is currently tracked by Git)."
    )


@patch("gitignore_explain.run_git")
@patch("gitignore_explain.check_tracked")
@patch("gitignore_explain.is_git_repo")
@patch("builtins.print")
def test_explain_ignore_not_ignored(
    mock_print: MagicMock,
    mock_is_repo: MagicMock,
    mock_tracked: MagicMock,
    mock_run_git: MagicMock,
) -> None:
    """Test explain_ignore when path is not ignored."""
    mock_is_repo.return_value = True
    mock_tracked.return_value = False
    mock_run_git.return_value = (1, "", "")  # check-ignore returns exit code 1

    explain_ignore(".", "file.txt")
    mock_print.assert_any_call("Status: NOT IGNORED (No ignore rules match this path).")


@patch("gitignore_explain.run_git")
@patch("gitignore_explain.check_tracked")
@patch("gitignore_explain.is_git_repo")
@patch("builtins.print")
def test_explain_ignore_failed_command(
    mock_print: MagicMock,
    mock_is_repo: MagicMock,
    mock_tracked: MagicMock,
    mock_run_git: MagicMock,
) -> None:
    """Test explain_ignore when git check-ignore command outputs stderr error."""
    mock_is_repo.return_value = True
    mock_tracked.return_value = False
    mock_run_git.return_value = (128, "", "fatal: error running command")

    with pytest.raises(SystemExit) as excinfo:
        explain_ignore(".", "file.txt")
    assert excinfo.value.code == 1
    mock_print.assert_any_call("Git check-ignore failed: fatal: error running command")


@patch("gitignore_explain.run_git")
@patch("gitignore_explain.check_tracked")
@patch("gitignore_explain.is_git_repo")
@patch("builtins.print")
def test_explain_ignore_bad_output(
    mock_print: MagicMock,
    mock_is_repo: MagicMock,
    mock_tracked: MagicMock,
    mock_run_git: MagicMock,
) -> None:
    """Test explain_ignore when git check-ignore outputs malformed line."""
    mock_is_repo.return_value = True
    mock_tracked.return_value = False
    mock_run_git.return_value = (0, "malformed output", "")

    with pytest.raises(SystemExit) as excinfo:
        explain_ignore(".", "file.txt")
    assert excinfo.value.code == 1
    mock_print.assert_any_call(
        "Could not parse git check-ignore output: malformed output"
    )


@patch("gitignore_explain.get_git_root")
@patch("gitignore_explain.run_git")
@patch("gitignore_explain.check_tracked")
@patch("gitignore_explain.is_git_repo")
@patch("builtins.print")
def test_explain_ignore_gitignore_rules(
    mock_print: MagicMock,
    mock_is_repo: MagicMock,
    mock_tracked: MagicMock,
    mock_run_git: MagicMock,
    mock_get_root: MagicMock,
) -> None:
    """Test explain_ignore output for various rule sources."""
    mock_is_repo.return_value = True
    mock_tracked.return_value = False
    mock_get_root.return_value = "/workspace"

    # Scenario 1: Local .gitignore
    mock_run_git.return_value = (0, ".gitignore:10:*.log   file.log", "")
    explain_ignore(".", "file.log")
    mock_print.assert_any_call("Status: IGNORED")
    mock_print.assert_any_call("Rule:   '*.log'")
    mock_print.assert_any_call("Source: .gitignore (Line 10)")

    # Scenario 2: local exclude file
    mock_run_git.return_value = (0, ".git/info/exclude:5:temp_*   temp_file", "")
    explain_ignore(".", "temp_file")
    mock_print.assert_any_call("Source: .git/info/exclude (Line 5)")

    # Scenario 3: Global gitignore
    mock_run_git.return_value = (0, "/global/ignore:2:*.o   file.o", "")
    explain_ignore(".", "file.o")
    mock_print.assert_any_call("Source: /global/ignore (Line 2)")


@patch("gitignore_explain.explain_ignore")
@patch("sys.argv")
def test_main_cli(mock_argv: MagicMock, mock_explain: MagicMock) -> None:
    """Test CLI parsing entry point."""
    mock_argv.__getitem__.side_effect = lambda x: [
        "gitignore_explain.py",
        "myfile.txt",
    ][x]
    mock_argv.__len__.return_value = 2

    main()
    mock_explain.assert_called_once_with(".", "myfile.txt")
