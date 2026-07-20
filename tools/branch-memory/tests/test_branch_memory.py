import os
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add target directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import branch_memory  # noqa: E402


def test_is_git_repo_true():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        assert branch_memory.is_git_repo("/fake/path") is True
        mock_run.assert_called_once_with(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd="/fake/path",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )


def test_is_git_repo_false():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        assert branch_memory.is_git_repo("/fake/path") is False


def test_is_git_repo_oserror():
    with patch("subprocess.run", side_effect=OSError("No git installed")):
        assert branch_memory.is_git_repo("/fake/path") is False


def test_get_main_branch_symbolic_ref():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="refs/remotes/origin/main\n"
        )
        assert branch_memory.get_main_branch("/fake/path") == "main"


def test_get_main_branch_fallback_verify():
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=1),
            MagicMock(returncode=0),
        ]
        assert branch_memory.get_main_branch("/fake/path") == "main"


def test_get_main_branch_fallback_master():
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=1),
            MagicMock(returncode=1),
            MagicMock(returncode=0),
        ]
        assert branch_memory.get_main_branch("/fake/path") == "master"


def test_get_main_branch_fallback_default():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        assert branch_memory.get_main_branch("/fake/path") == "main"


def test_get_branches():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="main|2 days ago\nfeature-xyz|5 hours ago\n"
        )
        branches = branch_memory.get_branches("/fake/path")
        assert branches == [("main", "2 days ago"), ("feature-xyz", "5 hours ago")]


def test_get_branches_failure():
    with patch("subprocess.run", side_effect=Exception("git error")):
        assert branch_memory.get_branches("/fake/path") == []


def test_get_branch_memory():
    def mock_run_se(cmd, **kwargs):
        if "log" in cmd:
            if "main..feature" in cmd:
                return MagicMock(
                    returncode=0, stdout="hash1 Commit A\nhash2 Commit B\n"
                )
            return MagicMock(returncode=0, stdout="hash3 Last Commit\n")
        if "diff" in cmd:
            if "--name-status" in cmd:
                return MagicMock(returncode=0, stdout="M\tfile1.py\nA\tfile2.py\n")
            diff_content = (
                "+ TODO: fix this bug\n"
                "+ JIRA-101 and #42 are related\n"
                "+ FIXME verify details\n"
                "- old line\n"
                "+ not a todo but GH-99 is mentioned\n"
                "+ BUG: crash on startup\n"
            )
            return MagicMock(returncode=0, stdout=diff_content)
        return MagicMock(returncode=1)

    with patch("subprocess.run", side_effect=mock_run_se):
        info = branch_memory.get_branch_memory("/fake/path", "feature", "main")
        assert info["commits"] == ["hash1 Commit A", "hash2 Commit B"]
        assert info["files_modified"] == ["M\tfile1.py", "A\tfile2.py"]
        assert "fix this bug" in info["todos"]
        assert "verify details" in info["todos"]
        assert "crash on startup" in info["todos"]
        assert info["issues"] == ["#42", "GH-99", "JIRA-101"]


def test_main_repo_path_not_exists(capsys):
    with patch("sys.argv", ["branch_memory.py", "/nonexistent/path"]), pytest.raises(
        SystemExit
    ) as excinfo:
        branch_memory.main()
    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert "Path does not exist" in captured.err


def test_main_not_git_repo(capsys, tmp_path):
    with patch("sys.argv", ["branch_memory.py", str(tmp_path)]), patch(
        "branch_memory.is_git_repo", return_value=False
    ), pytest.raises(SystemExit) as excinfo:
        branch_memory.main()
    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert "is not inside a Git repository" in captured.err


def test_main_no_branches(capsys, tmp_path):
    with patch("sys.argv", ["branch_memory.py", str(tmp_path)]), patch(
        "branch_memory.is_git_repo", return_value=True
    ), patch("branch_memory.get_main_branch", return_value="main"), patch(
        "branch_memory.get_branches", return_value=[]
    ), pytest.raises(
        SystemExit
    ) as excinfo:
        branch_memory.main()
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "No branches discovered" in captured.out


def test_main_success(capsys, tmp_path):
    branches = [("main", "1 day ago"), ("feature", "2 hours ago")]
    branch_mem_data = {
        "commits": ["hash1 Commit A", "hash2 Commit B"],
        "files_modified": ["M\tfile1.py", "A\tfile2.py", "D\tfile3.py", "M\tfile4.py"],
        "todos": ["todo 1", "todo 2", "todo 3", "todo 4"],
        "issues": ["GH-101"],
    }
    with patch("sys.argv", ["branch_memory.py", str(tmp_path)]), patch(
        "branch_memory.is_git_repo", return_value=True
    ), patch("branch_memory.get_main_branch", return_value="main"), patch(
        "branch_memory.get_branches", return_value=branches
    ), patch(
        "branch_memory.get_branch_memory", return_value=branch_mem_data
    ):
        branch_memory.main()

    captured = capsys.readouterr()
    assert "Branch: main" in captured.out
    assert "Branch: feature" in captured.out
    assert "Recent Commits:" in captured.out
    assert "- hash1 Commit A" in captured.out
    assert "Files Modified (4):" in captured.out
    assert "and 1 more files" in captured.out
    assert "Linked Issues: GH-101" in captured.out
    assert "Unfinished TODOs/FIXMEs (4):" in captured.out
    assert "* ... and 1 more." in captured.out
