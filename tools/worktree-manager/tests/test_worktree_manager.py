"""Unit tests for worktree_manager.py."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add script directory to path
sys.path.insert(0, "tools/worktree-manager")

# pylint: disable=wrong-import-position
from worktree_manager import (  # noqa: E402
    get_dir_size,
    get_worktree_list,
    is_git_repo,
    main,
    run_add,
    run_list,
    run_prune,
)


def test_is_git_repo_true():
    """Test is_git_repo returns True when git command succeeds."""
    mock_res = MagicMock()
    mock_res.returncode = 0
    with patch("subprocess.run", return_value=mock_res):
        assert is_git_repo("/dummy") is True


def test_is_git_repo_false():
    """Test is_git_repo returns False when git command fails."""
    mock_res = MagicMock()
    mock_res.returncode = 1
    with patch("subprocess.run", return_value=mock_res):
        assert is_git_repo("/dummy") is False


def test_is_git_repo_oserror():
    """Test is_git_repo returns False when git executable is not found."""
    with patch("subprocess.run", side_effect=OSError("not found")):
        assert is_git_repo("/dummy") is False


def test_get_dir_size_not_exists():
    """Test get_dir_size returns 0 if path does not exist."""
    with patch("os.path.exists", return_value=False):
        assert get_dir_size("/dummy/path") == 0


def test_get_dir_size_exists():
    """Test get_dir_size computes total size of files inside directory."""
    walk_data = [
        ("/dummy/dir", [], ["file1.txt", "file2.txt"]),
    ]
    with patch("os.path.exists", return_value=True), patch(
        "os.walk", return_value=walk_data
    ), patch("os.path.getsize", side_effect=[100, 250]):
        assert get_dir_size("/dummy/dir") == 350


def test_get_dir_size_oserror():
    """Test get_dir_size ignores files causing OSError."""
    walk_data = [
        ("/dummy/dir", [], ["file1.txt", "file2.txt"]),
    ]
    with patch("os.path.exists", return_value=True), patch(
        "os.walk", return_value=walk_data
    ), patch("os.path.getsize", side_effect=[100, OSError("permission denied")]):
        assert get_dir_size("/dummy/dir") == 100


def test_get_dir_size_walk_oserror():
    """Test get_dir_size handles OSError on directory walk gracefully."""
    with patch("os.path.exists", return_value=True), patch(
        "os.walk", side_effect=OSError("dir read error")
    ):
        assert get_dir_size("/dummy/dir") == 0


def test_get_worktree_list_failure():
    """Test get_worktree_list returns empty list when git returns non-zero code."""
    mock_res = MagicMock()
    mock_res.returncode = 128
    with patch("subprocess.run", return_value=mock_res):
        assert get_worktree_list("/dummy/repo") == []


def test_get_worktree_list_exception():
    """Test get_worktree_list handles exceptions and returns empty list."""
    with patch("subprocess.run", side_effect=OSError("error")):
        assert get_worktree_list("/dummy/repo") == []


def test_get_worktree_list_success():
    """Test get_worktree_list parses git worktree porcelain output successfully."""
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = (
        "worktree /dummy/repo/wt1\n"
        "commit abc1234567\n"
        "branch refs/heads/feature-branch\n"
        "\n"
        "worktree /dummy/repo/wt2\n"
        "commit def5678901\n"
        "branch refs/heads/master\n"
    )
    with patch("subprocess.run", return_value=mock_res):
        wts = get_worktree_list("/dummy/repo")
        assert len(wts) == 2
        assert wts[0]["path"] == "/dummy/repo/wt1"
        assert wts[0]["commit"] == "abc1234"
        assert wts[0]["branch"] == "feature-branch"

        assert wts[1]["path"] == "/dummy/repo/wt2"
        assert wts[1]["commit"] == "def5678"
        assert wts[1]["branch"] == "master"


@patch("worktree_manager.get_worktree_list", return_value=[])
@patch("builtins.print")
def test_run_list_empty(mock_print, mock_list):
    """Test run_list prints hint when there are no worktrees."""
    run_list("/dummy/repo")
    mock_print.assert_any_call("[-] No Git worktrees registered in this repository.")


@patch("worktree_manager.get_worktree_list")
@patch("os.path.exists")
@patch("worktree_manager.get_dir_size", return_value=1024 * 1024 * 5)
@patch("builtins.print")
def test_run_list_active_and_abandoned(mock_print, mock_size, mock_exists, mock_list):
    """Test run_list prints active/abandoned worktrees correctly."""
    mock_list.return_value = [
        {
            "path": "/dummy/repo/active_worktree_with_a_very_long_path_name",
            "branch": "active-branch",
        },
        {"path": "/dummy/repo/abandoned_wt", "branch": "abandoned-branch"},
    ]
    mock_exists.side_effect = [True, False]

    run_list("/dummy/repo")

    printed_lines = [call.args[0] for call in mock_print.call_args_list if call.args]
    assert any("..." in line for line in printed_lines)
    assert any("Active" in line for line in printed_lines)
    assert any("5.0 MB" in line for line in printed_lines)
    assert any("Abandoned" in line for line in printed_lines)


@patch("os.path.exists", return_value=True)
@patch("builtins.print")
def test_run_add_path_exists(mock_print, mock_exists):
    """Test run_add exit code when target path already exists."""
    with pytest.raises(SystemExit) as excinfo:
        run_add("/dummy/repo", "wt-name", None)
    assert excinfo.value.code == 1
    expected_path = os.path.join("/dummy", "wt-name")
    mock_print.assert_any_call(
        f"Error: Target path already exists: {expected_path}", file=sys.stderr
    )


@patch("os.path.exists", return_value=False)
@patch("subprocess.run")
@patch("builtins.print")
def test_run_add_new_branch(mock_print, mock_run, mock_exists):
    """Test run_add triggers creation with new branch if no branch specified."""
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = "worktree added info"
    mock_run.return_value = mock_res

    run_add("/dummy/repo", "wt-name", None)

    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert "-b" in args
    assert "wt-name" in args
    mock_print.assert_any_call("[+] Success: Worktree created.")


@patch("os.path.exists", return_value=False)
@patch("subprocess.run")
@patch("builtins.print")
def test_run_add_existing_branch(mock_print, mock_run, mock_exists):
    """Test run_add triggers checkout of existing branch if branch specified."""
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = "worktree added info"
    mock_run.return_value = mock_res

    run_add("/dummy/repo", "wt-name", "main")

    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert "main" in args
    assert "-b" not in args


@patch("os.path.exists", return_value=False)
@patch("subprocess.run")
@patch("builtins.print")
def test_run_add_failure(mock_print, mock_run, mock_exists):
    """Test run_add exits with command exit code when git command fails."""
    mock_res = MagicMock()
    mock_res.returncode = 128
    mock_res.stdout = ""
    mock_res.stderr = "git worktree add failed reason"
    mock_run.return_value = mock_res

    with pytest.raises(SystemExit) as excinfo:
        run_add("/dummy/repo", "wt-name", None)
    assert excinfo.value.code == 128
    mock_print.assert_any_call("git worktree add failed reason", file=sys.stderr)


@patch("os.path.exists", return_value=False)
@patch("subprocess.run", side_effect=OSError("binary missing"))
@patch("builtins.print")
def test_run_add_exception(mock_print, mock_run, mock_exists):
    """Test run_add prints error message on command exception."""
    run_add("/dummy/repo", "wt-name", None)
    mock_print.assert_any_call(
        "Error executing command: binary missing", file=sys.stderr
    )


@patch("subprocess.run")
@patch("builtins.print")
def test_run_prune_success(mock_print, mock_run):
    """Test run_prune succeeds."""
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_run.return_value = mock_res

    run_prune("/dummy/repo")
    mock_print.assert_any_call("[+] Success: Stale worktree records pruned.")


@patch("subprocess.run")
@patch("builtins.print")
def test_run_prune_failure(mock_print, mock_run):
    """Test run_prune outputs stderr on command failure."""
    mock_res = MagicMock()
    mock_res.returncode = 1
    mock_res.stderr = "prune error detail"
    mock_run.return_value = mock_res

    run_prune("/dummy/repo")
    mock_print.assert_any_call("prune error detail", file=sys.stderr)


@patch("subprocess.run", side_effect=OSError("system error"))
@patch("builtins.print")
def test_run_prune_exception(mock_print, mock_run):
    """Test run_prune outputs system errors safely."""
    run_prune("/dummy/repo")
    mock_print.assert_any_call("Error executing prune: system error", file=sys.stderr)


@patch("worktree_manager.is_git_repo", return_value=False)
@patch("os.getcwd", return_value="/dummy/repo")
@patch("builtins.print")
def test_main_not_git_repo(mock_print, mock_cwd, mock_is_git):
    """Test main exits with 1 if not inside a git repository."""
    with patch("sys.argv", ["worktree_manager", "list"]), pytest.raises(
        SystemExit
    ) as excinfo:
        main()
    assert excinfo.value.code == 1
    mock_print.assert_any_call(
        "Error: Current directory '/dummy/repo' is not inside a Git repository.",
        file=sys.stderr,
    )


@patch("worktree_manager.is_git_repo", return_value=True)
@patch("os.getcwd", return_value="/dummy/repo")
@patch("worktree_manager.run_list")
def test_main_subcommand_list(mock_list, mock_cwd, mock_is_git):
    """Test main triggers run_list for 'list' subcommand."""
    with patch("sys.argv", ["worktree_manager", "list"]):
        main()
        mock_list.assert_called_once_with("/dummy/repo")


@patch("worktree_manager.is_git_repo", return_value=True)
@patch("os.getcwd", return_value="/dummy/repo")
@patch("worktree_manager.run_add")
def test_main_subcommand_add(mock_add, mock_cwd, mock_is_git):
    """Test main triggers run_add for 'add' subcommand."""
    with patch("sys.argv", ["worktree_manager", "add", "new-wt", "some-branch"]):
        main()
        mock_add.assert_called_once_with("/dummy/repo", "new-wt", "some-branch")


@patch("worktree_manager.is_git_repo", return_value=True)
@patch("os.getcwd", return_value="/dummy/repo")
@patch("worktree_manager.run_prune")
def test_main_subcommand_prune(mock_prune, mock_cwd, mock_is_git):
    """Test main triggers run_prune for 'prune' subcommand."""
    with patch("sys.argv", ["worktree_manager", "prune"]):
        main()
        mock_prune.assert_called_once_with("/dummy/repo")


@patch("worktree_manager.is_git_repo", return_value=True)
@patch("os.getcwd", return_value="/dummy/repo")
@patch("worktree_manager.run_list")
def test_main_no_subcommand(mock_list, mock_cwd, mock_is_git):
    """Test main defaults to list command if no subcommand provided."""
    with patch("sys.argv", ["worktree_manager"]):
        main()
        mock_list.assert_called_once_with("/dummy/repo")
