import os
import sys
from unittest.mock import ANY, MagicMock, patch

import pytest

# Add parent directory of this test file to sys.path so we can import stash_manager
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import stash_manager  # noqa: E402


def test_is_git_repo_success():
    mock_res = MagicMock()
    mock_res.returncode = 0
    with patch("subprocess.run", return_value=mock_res):
        assert stash_manager.is_git_repo("/dummy/path")


def test_is_git_repo_failure():
    mock_res = MagicMock()
    mock_res.returncode = 1
    with patch("subprocess.run", return_value=mock_res):
        assert not stash_manager.is_git_repo("/dummy/path")


def test_is_git_repo_oserror():
    with patch("subprocess.run", side_effect=OSError("git not found")):
        assert not stash_manager.is_git_repo("/dummy/path")


def test_get_current_branch_success():
    mock_res = MagicMock()
    mock_res.stdout = "  feature-branch \n"
    with patch("subprocess.run", return_value=mock_res):
        assert stash_manager.get_current_branch("/dummy/path") == "feature-branch"


def test_get_current_branch_detached():
    mock_res = MagicMock()
    mock_res.stdout = ""
    with patch("subprocess.run", return_value=mock_res):
        assert stash_manager.get_current_branch("/dummy/path") == "HEAD detached"


def test_get_current_branch_exception():
    with patch("subprocess.run", side_effect=OSError("error")):
        assert stash_manager.get_current_branch("/dummy/path") == "Unknown"


def test_get_stash_list():
    mock_res = MagicMock()
    mock_res.stdout = (
        "stash@{0}: WIP on main: 1a2b3c4 Commit Message\n"
        "stash@{1}: On feature-branch: Description\n"
    )
    with patch("subprocess.run", return_value=mock_res):
        stashes = stash_manager.get_stash_list("/dummy/path")
        assert len(stashes) == 2
        assert stashes[0] == {
            "index": 0,
            "id": "stash@{0}",
            "branch": "main",
            "description": "WIP on main: 1a2b3c4 Commit Message",
        }
        assert stashes[1] == {
            "index": 1,
            "id": "stash@{1}",
            "branch": "feature-branch",
            "description": "On feature-branch: Description",
        }


def test_get_stash_list_empty():
    mock_res = MagicMock()
    mock_res.stdout = ""
    with patch("subprocess.run", return_value=mock_res):
        assert stash_manager.get_stash_list("/dummy/path") == []


def test_get_stash_details():
    def mock_subprocess_run(cmd, *args, **kwargs):
        res = MagicMock()
        res.returncode = 0
        if "show" in cmd and "-s" in cmd:
            res.stdout = "2026-07-19 22:53:24\n"
        elif "show" in cmd and "--name-only" in cmd:
            res.stdout = "file1.py\nfile2.txt\n"
        elif "show" in cmd and "-p" in cmd:
            res.stdout = "diff data..."
        return res

    with patch("subprocess.run", side_effect=mock_subprocess_run):
        details = stash_manager.get_stash_details("/dummy/path", "stash@{0}")
        assert details["date"] == "2026-07-19 22:53:24"
        assert details["files"] == ["file1.py", "file2.txt"]
        assert details["diff"] == "diff data..."


def test_evaluate_conflict_risk_none():
    assert stash_manager.evaluate_conflict_risk("/dummy/path", []) == "None"


def test_evaluate_conflict_risk_low():
    mock_res = MagicMock()
    mock_res.stdout = " M app.py\n"
    with patch("subprocess.run", return_value=mock_res):
        risk = stash_manager.evaluate_conflict_risk("/dummy/path", ["other_file.py"])
        assert risk == "Low"


def test_evaluate_conflict_risk_high():
    mock_res = MagicMock()
    mock_res.stdout = " M app.py\n M test.py\n"
    with patch("subprocess.run", return_value=mock_res):
        risk = stash_manager.evaluate_conflict_risk("/dummy/path", ["app.py"])
        assert "HIGH" in risk
        assert "app.py" in risk


def test_main_path_not_exists():
    with patch("sys.argv", ["stash_manager.py", "nonexistent_path"]):
        with pytest.raises(SystemExit) as exc:
            stash_manager.main()
        assert exc.value.code == 1


@patch("os.path.exists", return_value=True)
@patch("stash_manager.is_git_repo", return_value=False)
def test_main_not_git_repo(mock_is_git, mock_exists):
    with patch("sys.argv", ["stash_manager.py", "/dummy/path"]):
        with pytest.raises(SystemExit) as exc:
            stash_manager.main()
        assert exc.value.code == 1


@patch("os.path.exists", return_value=True)
@patch("stash_manager.is_git_repo", return_value=True)
@patch("stash_manager.get_stash_details")
def test_main_preview(mock_details, mock_is_git, mock_exists, capsys):
    mock_details.return_value = {
        "date": "2026-07-19 12:00:00",
        "files": ["file1.py"],
        "diff": "some diff preview",
    }
    with patch("sys.argv", ["stash_manager.py", "--preview", "0"]):
        with pytest.raises(SystemExit) as exc:
            stash_manager.main()
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "STASH DETAILS FOR: stash@{0}" in captured.out
        assert "Created: 2026-07-19 12:00:00" in captured.out
        assert "some diff preview" in captured.out


@patch("os.path.exists", return_value=True)
@patch("stash_manager.is_git_repo", return_value=True)
@patch("stash_manager.get_stash_details")
@patch("stash_manager.evaluate_conflict_risk")
@patch("subprocess.run")
def test_main_apply_low_risk(
    mock_run, mock_risk, mock_details, mock_is_git, mock_exists, capsys
):
    mock_details.return_value = {"files": ["file1.py"]}
    mock_risk.return_value = "Low"
    mock_run_res = MagicMock()
    mock_run_res.returncode = 0
    mock_run_res.stdout = "Applied successfully"
    mock_run.return_value = mock_run_res

    with patch("sys.argv", ["stash_manager.py", "--apply", "1"]):
        with pytest.raises(SystemExit) as exc:
            stash_manager.main()
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "Conflict Risk: Low" in captured.out
        assert "Applying stash@{1}..." in captured.out
        assert "Applied successfully" in captured.out


@patch("os.path.exists", return_value=True)
@patch("stash_manager.is_git_repo", return_value=True)
@patch("stash_manager.get_stash_details")
@patch("stash_manager.evaluate_conflict_risk")
@patch("builtins.input", return_value="n")
def test_main_apply_high_risk_abort(
    mock_input, mock_risk, mock_details, mock_is_git, mock_exists, capsys
):
    mock_details.return_value = {"files": ["file1.py"]}
    mock_risk.return_value = "HIGH"

    with patch("sys.argv", ["stash_manager.py", "--apply", "1"]):
        with pytest.raises(SystemExit) as exc:
            stash_manager.main()
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "Conflict Risk: HIGH" in captured.out
        assert "Operation aborted" in captured.out


@patch("os.path.exists", return_value=True)
@patch("stash_manager.is_git_repo", return_value=True)
@patch("stash_manager.get_stash_details")
@patch("stash_manager.evaluate_conflict_risk")
@patch("builtins.input", return_value="y")
@patch("subprocess.run")
def test_main_apply_high_risk_proceed(
    mock_run, mock_input, mock_risk, mock_details, mock_is_git, mock_exists
):
    mock_details.return_value = {"files": ["file1.py"]}
    mock_risk.return_value = "HIGH"
    mock_run_res = MagicMock()
    mock_run_res.returncode = 0
    mock_run.return_value = mock_run_res

    with patch("sys.argv", ["stash_manager.py", "--apply", "1"]):
        with pytest.raises(SystemExit) as exc:
            stash_manager.main()
        assert exc.value.code == 0
        mock_run.assert_called_with(
            ["git", "stash", "apply", "stash@{1}"],
            cwd=ANY,
            stdout=ANY,
            stderr=ANY,
            text=True,
            check=False,
        )


@patch("os.path.exists", return_value=True)
@patch("stash_manager.is_git_repo", return_value=True)
@patch("stash_manager.get_stash_list")
@patch("stash_manager.get_current_branch", return_value="main")
@patch("stash_manager.get_stash_details")
@patch("stash_manager.evaluate_conflict_risk", return_value="Low")
def test_main_list_stashes(
    mock_risk, mock_details, mock_branch, mock_list, mock_is_git, mock_exists, capsys
):
    mock_list.return_value = [
        {"index": 0, "id": "stash@{0}", "branch": "feature1", "description": "desc 1"},
        {"index": 1, "id": "stash@{1}", "branch": "feature2", "description": "desc 2"},
    ]
    mock_details.return_value = {"files": ["file1.py"]}

    with patch("sys.argv", ["stash_manager.py"]):
        stash_manager.main()
        captured = capsys.readouterr()
        assert "GIT STASHES AUDIT FOR:" in captured.out
        assert "Active Branch: main" in captured.out
        assert "feature1" in captured.out
        assert "feature2" in captured.out
