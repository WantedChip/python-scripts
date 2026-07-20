import os
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

# Ensure target directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import stash_conflict_preview  # noqa: E402


def test_is_git_repo_success():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        assert stash_conflict_preview.is_git_repo("/dummy") is True


def test_is_git_repo_failure():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        assert stash_conflict_preview.is_git_repo("/dummy") is False


def test_is_git_repo_oserror():
    with patch("subprocess.run", side_effect=OSError):
        assert stash_conflict_preview.is_git_repo("/dummy") is False


def test_get_stashes_success():
    mock_run_res = MagicMock()
    mock_run_res.stdout = "stash@{0}: On master: WIP\nstash@{1}: On master: debug\n"
    with patch("subprocess.run", return_value=mock_run_res):
        stashes = stash_conflict_preview.get_stashes("/dummy")
        assert stashes == ["stash@{0}: On master: WIP", "stash@{1}: On master: debug"]


def test_get_stashes_empty_and_exception():
    with patch("subprocess.run", side_effect=Exception):
        assert stash_conflict_preview.get_stashes("/dummy") == []


def test_parse_diff_hunks():
    diff_output = """diff --git a/src/app.py b/src/app.py
index 12345..67890 100644
--- a/src/app.py
+++ b/src/app.py
@@ -10,3 +12,4 @@
+added line 1
+added line 2
diff --git a/tests/test_app.py b/tests/test_app.py
index 54321..09876 100644
--- a/tests/test_app.py
+++ b/tests/test_app.py
@@ -50 +50,2 @@
+test line 1
+test line 2
"""
    result = stash_conflict_preview.parse_diff_hunks(diff_output)
    assert result == {"src/app.py": [(12, 15)], "tests/test_app.py": [(50, 51)]}


def test_get_stash_diff_ranges():
    mock_res = MagicMock(returncode=0, stdout="+++ b/file.py\n@@ -1,2 +1,3 @@\n+line\n")
    with patch("subprocess.run", return_value=mock_res):
        ranges = stash_conflict_preview.get_stash_diff_ranges("/dummy", "stash@{0}")
        assert "file.py" in ranges
        assert ranges["file.py"] == [(1, 3)]


def test_get_stash_diff_ranges_failure():
    mock_res = MagicMock(returncode=1)
    with patch("subprocess.run", return_value=mock_res):
        res = stash_conflict_preview.get_stash_diff_ranges("/dummy", "stash@{0}")
        assert res == {}

    with patch("subprocess.run", side_effect=Exception):
        res = stash_conflict_preview.get_stash_diff_ranges("/dummy", "stash@{0}")
        assert res == {}


def test_get_local_diff_ranges():
    mock_res = MagicMock(returncode=0, stdout="+++ b/file.py\n@@ -5,2 +5,2 @@\n+line\n")
    with patch("subprocess.run", return_value=mock_res) as mock_run:
        ranges = stash_conflict_preview.get_local_diff_ranges("/dummy")
        assert ranges["file.py"] == [(5, 6)]
        mock_run.assert_called_once_with(
            ["git", "diff", "HEAD"],
            cwd="/dummy",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )


def test_get_head_diff_ranges():
    mock_res = MagicMock(
        returncode=0, stdout="+++ b/file.py\n@@ -10,1 +10,1 @@\n+line\n"
    )
    with patch("subprocess.run", return_value=mock_res) as mock_run:
        ranges = stash_conflict_preview.get_head_diff_ranges("/dummy", "stash@{0}")
        assert ranges["file.py"] == [(10, 10)]
        mock_run.assert_called_once_with(
            ["git", "diff", "stash@{0}^1", "HEAD"],
            cwd="/dummy",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )


def test_check_ranges_overlap():
    # Overlapping ranges
    r1 = [(10, 20)]
    r2 = [(15, 25)]
    res = stash_conflict_preview.check_ranges_overlap(r1, r2)
    assert res == [((10, 20), (15, 25))]

    # Adjacent ranges within padding
    r3 = [(22, 30)]
    res = stash_conflict_preview.check_ranges_overlap(r1, r3)
    assert res == [((10, 20), (22, 30))]

    # Far apart (no overlap)
    r4 = [(23, 30)]
    assert stash_conflict_preview.check_ranges_overlap(r1, r4) == []


def raise_exit(code=0):
    raise SystemExit(code)


def test_main_path_not_exists():
    with patch("os.path.exists", return_value=False), patch(
        "sys.argv", ["stash_conflict_preview.py"]
    ), patch("sys.exit", side_effect=raise_exit):
        with pytest.raises(SystemExit) as excinfo:
            stash_conflict_preview.main()
        assert excinfo.value.code == 1


def test_main_not_git_repo():
    with patch("os.path.exists", return_value=True), patch(
        "sys.argv", ["stash_conflict_preview.py"]
    ), patch("stash_conflict_preview.is_git_repo", return_value=False), patch(
        "sys.exit", side_effect=raise_exit
    ):
        with pytest.raises(SystemExit) as excinfo:
            stash_conflict_preview.main()
        assert excinfo.value.code == 1


def test_main_no_stashes(capsys):
    with patch("os.path.exists", return_value=True), patch(
        "sys.argv", ["stash_conflict_preview.py"]
    ), patch("stash_conflict_preview.is_git_repo", return_value=True), patch(
        "stash_conflict_preview.get_stashes", return_value=[]
    ), patch(
        "sys.exit", side_effect=raise_exit
    ):
        with pytest.raises(SystemExit) as excinfo:
            stash_conflict_preview.main()
        assert excinfo.value.code == 0
        out, err = capsys.readouterr()
        assert "No stashes found" in out


def test_main_stash_index_out_of_range():
    with patch("os.path.exists", return_value=True), patch(
        "stash_conflict_preview.is_git_repo", return_value=True
    ), patch("stash_conflict_preview.get_stashes", return_value=["stash 0"]), patch(
        "sys.argv", ["stash_conflict_preview.py", "2"]
    ), patch(
        "sys.exit", side_effect=raise_exit
    ):
        with pytest.raises(SystemExit) as excinfo:
            stash_conflict_preview.main()
        assert excinfo.value.code == 1


def test_main_no_stash_diff(capsys):
    with patch("os.path.exists", return_value=True), patch(
        "sys.argv", ["stash_conflict_preview.py"]
    ), patch("stash_conflict_preview.is_git_repo", return_value=True), patch(
        "stash_conflict_preview.get_stashes", return_value=["stash 0"]
    ), patch(
        "stash_conflict_preview.get_stash_diff_ranges", return_value={}
    ), patch(
        "sys.exit", side_effect=raise_exit
    ):
        with pytest.raises(SystemExit) as excinfo:
            stash_conflict_preview.main()
        assert excinfo.value.code == 0
        out, err = capsys.readouterr()
        assert "No code modifications found in target stash" in out


def test_main_clean_merge(capsys):
    with patch("os.path.exists", return_value=True), patch(
        "sys.argv", ["stash_conflict_preview.py"]
    ), patch("stash_conflict_preview.is_git_repo", return_value=True), patch(
        "stash_conflict_preview.get_stashes", return_value=["stash 0"]
    ), patch(
        "stash_conflict_preview.get_stash_diff_ranges",
        return_value={"file.py": [(10, 15)]},
    ), patch(
        "stash_conflict_preview.get_local_diff_ranges",
        return_value={"file.py": [(30, 40)]},
    ), patch(
        "stash_conflict_preview.get_head_diff_ranges", return_value={}
    ), patch(
        "sys.exit", side_effect=raise_exit
    ) as mock_exit:

        stash_conflict_preview.main()
        mock_exit.assert_not_called()

        out, err = capsys.readouterr()
        assert "Clean merge predicted." in out
        assert "Status: CLEAN." in out


def test_main_conflicts_detected(capsys):
    with patch("os.path.exists", return_value=True), patch(
        "sys.argv", ["stash_conflict_preview.py"]
    ), patch("stash_conflict_preview.is_git_repo", return_value=True), patch(
        "stash_conflict_preview.get_stashes", return_value=["stash 0"]
    ), patch(
        "stash_conflict_preview.get_stash_diff_ranges",
        return_value={"file.py": [(10, 15)]},
    ), patch(
        "stash_conflict_preview.get_local_diff_ranges",
        return_value={"file.py": [(12, 13)]},
    ), patch(
        "stash_conflict_preview.get_head_diff_ranges",
        return_value={"file.py": [(11, 14)]},
    ), patch(
        "sys.exit", side_effect=raise_exit
    ) as mock_exit:

        stash_conflict_preview.main()
        mock_exit.assert_not_called()

        out, err = capsys.readouterr()
        assert "LIKELY MERGE CONFLICT DETECTED!" in out
        assert "Overlaps local unstaged changes:" in out
        assert "Overlaps commits made since stash:" in out
        assert "Status: HIGH RISK." in out
