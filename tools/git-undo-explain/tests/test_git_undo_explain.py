"""Unit tests for the git-undo-explain script."""

import os
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

# Insert parent dir to PATH to support folder-based import
sys.path.insert(0, "tools/git-undo-explain")

# pylint: disable=wrong-import-position
from git_undo_explain import execute_recovery, is_git_repo, main  # noqa: E402


def test_is_git_repo_success():
    with patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run.return_value = mock_res

        assert is_git_repo("mock_path") is True
        mock_run.assert_called_once_with(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd="mock_path",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )


def test_is_git_repo_failure():
    with patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_run.return_value = mock_res

        assert is_git_repo("mock_path") is False


def test_is_git_repo_oserror():
    with patch("subprocess.run", side_effect=OSError("git not found")):
        assert is_git_repo("mock_path") is False


def test_execute_recovery_success():
    with patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "output"
        mock_res.stderr = ""
        mock_run.return_value = mock_res

        commands = ["# instruction", "git status"]
        execute_recovery(commands, "mock_path")

        # "# instruction" should be skipped, so run is called once
        mock_run.assert_called_once_with(
            "git status",
            shell=True,
            cwd="mock_path",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )


def test_execute_recovery_failure():
    with patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_res.stdout = ""
        mock_res.stderr = "error"
        mock_run.return_value = mock_res

        # Second command should be aborted because the first one fails (exits non-zero)
        commands = ["git checkout main", "git pull"]
        execute_recovery(commands, "mock_path")

        mock_run.assert_called_once_with(
            "git checkout main",
            shell=True,
            cwd="mock_path",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )


@patch("os.path.exists", return_value=False)
def test_main_path_not_exists(mock_exists):
    with patch("sys.argv", ["git_undo_explain.py", "missing_path"]), pytest.raises(
        SystemExit
    ) as exc:
        main()
    assert exc.value.code == 1


@patch("os.path.exists", return_value=True)
@patch("git_undo_explain.is_git_repo", return_value=False)
def test_main_not_git_repo(mock_git, mock_exists):
    with patch("sys.argv", ["git_undo_explain.py", "mock_path"]), pytest.raises(
        SystemExit
    ) as exc:
        main()
    assert exc.value.code == 1


@patch("os.path.exists", return_value=True)
@patch("git_undo_explain.is_git_repo", return_value=True)
@patch("git_undo_explain.execute_recovery")
def test_main_scenario_direct_yes(mock_recovery, mock_git, mock_exists):
    with patch(
        "sys.argv", ["git_undo_explain.py", "mock_path", "--scenario", "2", "--yes"]
    ):
        main()
        mock_recovery.assert_called_once_with(
            ["git reset --soft HEAD~1"], os.path.abspath("mock_path")
        )


@patch("os.path.exists", return_value=True)
@patch("git_undo_explain.is_git_repo", return_value=True)
@patch("git_undo_explain.execute_recovery")
def test_main_scenario_interactive_yes(mock_recovery, mock_git, mock_exists):
    # Mock inputs: select scenario 3, then confirm 'y'
    inputs = ["3", "y"]
    with patch("sys.argv", ["git_undo_explain.py", "mock_path"]), patch(
        "builtins.input", side_effect=inputs
    ):
        main()
        mock_recovery.assert_called_once_with(
            ["git reset --hard HEAD~1"], os.path.abspath("mock_path")
        )


@patch("os.path.exists", return_value=True)
@patch("git_undo_explain.is_git_repo", return_value=True)
@patch("git_undo_explain.execute_recovery")
def test_main_scenario_interactive_abort(mock_recovery, mock_git, mock_exists):
    # Mock inputs: select scenario 3, then abort with 'n'
    inputs = ["3", "n"]
    with patch("sys.argv", ["git_undo_explain.py", "mock_path"]), patch(
        "builtins.input", side_effect=inputs
    ), pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    mock_recovery.assert_not_called()


@patch("os.path.exists", return_value=True)
@patch("git_undo_explain.is_git_repo", return_value=True)
@patch("git_undo_explain.execute_recovery")
def test_main_scenario_invalid_choice(mock_recovery, mock_git, mock_exists):
    inputs = ["9"]
    with patch("sys.argv", ["git_undo_explain.py", "mock_path"]), patch(
        "builtins.input", side_effect=inputs
    ), pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    mock_recovery.assert_not_called()


@patch("os.path.exists", return_value=True)
@patch("git_undo_explain.is_git_repo", return_value=True)
@patch("git_undo_explain.execute_recovery")
def test_main_scenario_keyboard_interrupt(mock_recovery, mock_git, mock_exists):
    with patch("sys.argv", ["git_undo_explain.py", "mock_path"]), patch(
        "builtins.input", side_effect=KeyboardInterrupt
    ), pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    mock_recovery.assert_not_called()


@patch("os.path.exists", return_value=True)
@patch("git_undo_explain.is_git_repo", return_value=True)
@patch("git_undo_explain.execute_recovery")
def test_main_scenario_5_custom_file(mock_recovery, mock_git, mock_exists):
    inputs = ["secrets.txt"]
    with patch(
        "sys.argv", ["git_undo_explain.py", "mock_path", "--scenario", "5", "--yes"]
    ), patch("builtins.input", side_effect=inputs):
        main()
        mock_recovery.assert_called_once_with(
            ["git rm --cached secrets.txt", "echo secrets.txt >> .gitignore"],
            os.path.abspath("mock_path"),
        )


@patch("os.path.exists", return_value=True)
@patch("git_undo_explain.is_git_repo", return_value=True)
@patch("git_undo_explain.execute_recovery")
def test_main_scenario_5_empty_file_abort(mock_recovery, mock_git, mock_exists):
    inputs = [""]
    with patch(
        "sys.argv", ["git_undo_explain.py", "mock_path", "--scenario", "5", "--yes"]
    ), patch("builtins.input", side_effect=inputs), pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    mock_recovery.assert_not_called()
