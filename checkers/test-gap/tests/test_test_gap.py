"""Unit tests for the test-gap script."""

import os
import sys
from unittest.mock import MagicMock, mock_open, patch

import pytest

# Insert parent dir to PATH to support folder-based import
sys.path.insert(0, "checkers/test-gap")

# pylint: disable=wrong-import-position
from test_gap import (  # noqa: E402
    check_coverage_gaps,
    get_repo_root,
    parse_diff,
    print_report,
)

SAMPLE_DIFF = """diff --git a/checkers/linter.py b/checkers/linter.py
index 123456..789abc 100644
--- a/checkers/linter.py
+++ b/checkers/linter.py
@@ -10 +10,3 @@
+added line 1
+added line 2
+added line 3
@@ -35,2 +37,2 @@
-old line
+new line
diff --git a/README.md b/README.md
index abcdef..123456 100644
--- a/README.md
+++ b/README.md
@@ -1 +1,2 @@
+added README line
"""


def test_parse_diff() -> None:
    """Test parsing of git diff chunks for added lines."""
    changed = parse_diff(SAMPLE_DIFF)
    # README.md should be filtered out as it is not a .py file
    assert "README.md" not in changed
    assert "checkers/linter.py" in changed

    # In checkers/linter.py:
    # Chunk 1: starts at 10, count 3 -> lines 10, 11, 12
    # Chunk 2: starts at 37, count 2 -> lines 37, 38
    lines = changed["checkers/linter.py"]
    assert lines == {10, 11, 12, 37, 38}


def test_check_coverage_gaps() -> None:
    """Test comparing modified lines with test coverage data."""
    changed_files = {"checkers/linter.py": {10, 11, 12, 37, 38}}

    # Mock coverage Coverage class and CoverageData
    mock_cov = MagicMock()
    mock_data = MagicMock()

    # Mock lines 10 and 11 as executed, leaving 12, 37, 38 as uncovered gaps
    mock_data.lines.return_value = [10, 11, 99]  # 99 is executed but not modified
    mock_cov.get_data.return_value = mock_data

    with patch("coverage.Coverage", return_value=mock_cov):
        reports = check_coverage_gaps("/repo/root", changed_files, ".coverage")

        assert len(reports) == 1
        rep = reports[0]
        assert rep["file"] == "checkers/linter.py"
        assert rep["total_changed"] == 5
        assert rep["covered_changed"] == 2
        assert rep["uncovered_lines"] == [12, 37, 38]
        assert rep["coverage_pct"] == 40.0


def test_print_report(capsys: pytest.CaptureFixture[str]) -> None:
    """Test printing gap reports in text and markdown formats."""
    reports = [
        {
            "file": "checkers/linter.py",
            "total_changed": 5,
            "covered_changed": 2,
            "uncovered_lines": [12, 37, 38],
            "coverage_pct": 40.0,
        }
    ]

    # Text report
    print_report(reports, "text")
    captured = capsys.readouterr()
    assert "TEST COVERAGE GAP REPORT" in captured.out
    assert "checkers/linter.py" in captured.out
    assert "Missing lines: [12, 37, 38]" in captured.out

    # Markdown report
    print_report(reports, "markdown")
    captured = capsys.readouterr()
    assert "# Test Coverage Gap Report" in captured.out
    assert "| `checkers/linter.py` | 5 | 2 | 3 | 40.0% | `12, 37, 38` |" in captured.out


@patch("subprocess.run")
def test_get_repo_root(mock_run: MagicMock) -> None:
    """Test fetching repository root path."""
    mock_run.return_value.stdout = "/path/to/repo\n"
    assert get_repo_root() == "/path/to/repo"


def test_edge_cases_and_main() -> None:
    """Test test-gap edge cases and main function."""
    # 1. get_repo_root failure fallback
    with patch("subprocess.run", side_effect=FileNotFoundError):
        assert get_repo_root() == os.getcwd()

    # 2. get_git_diff with and without ref, and failure fallback
    from test_gap import get_git_diff

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = "diff text"
        assert get_git_diff("origin/main") == "diff text"
        mock_run.assert_called_with(
            ["git", "diff", "-U0", "origin/main"],
            capture_output=True,
            text=True,
            check=True,
        )

        assert get_git_diff() == "diff text"
        mock_run.assert_called_with(
            ["git", "diff", "-U0"], capture_output=True, text=True, check=True
        )

    with patch("subprocess.run", side_effect=FileNotFoundError):
        assert get_git_diff() == ""

    # 3. check_coverage_gaps load failure
    with patch("coverage.Coverage.load", side_effect=Exception("Load failed")):
        reports = check_coverage_gaps("/repo/root", {"checkers/linter.py": {10}})
        assert len(reports) == 1
        assert reports[0]["uncovered_lines"] == [10]

    # 4. test_gap main CLI tests
    from test_gap import main as test_gap_main

    # Case: Diff file does not exist
    with patch("sys.argv", ["test-gap", "--diff-file", "nonexistent.diff"]):
        with pytest.raises(SystemExit) as exc:
            test_gap_main()
        assert exc.value.code == 1

    # Case: Empty diff
    with patch("sys.argv", ["test-gap"]), patch(
        "test_gap.get_git_diff", return_value=""
    ):
        with pytest.raises(SystemExit) as exc:
            test_gap_main()
        assert exc.value.code == 0

    # Case: No Python files in diff
    with patch("sys.argv", ["test-gap"]), patch(
        "test_gap.get_git_diff", return_value="diff --git a/README.md b/README.md\n"
    ):
        with pytest.raises(SystemExit) as exc:
            test_gap_main()
        assert exc.value.code == 0

    # Case: Gaps found (exit code 1)
    with patch("sys.argv", ["test-gap", "--diff-file", "wf.diff"]), patch(
        "builtins.open", mock_open(read_data=SAMPLE_DIFF)
    ), patch("os.path.exists", return_value=True), patch(
        "test_gap.check_coverage_gaps",
        return_value=[
            {
                "file": "x.py",
                "uncovered_lines": [1],
                "total_changed": 1,
                "covered_changed": 0,
                "coverage_pct": 0.0,
            }
        ],
    ):
        with pytest.raises(SystemExit) as exc:
            test_gap_main()
        assert exc.value.code == 1

    # Case: No gaps found (exit code 0)
    with patch("sys.argv", ["test-gap", "--diff-file", "wf.diff"]), patch(
        "builtins.open", mock_open(read_data=SAMPLE_DIFF)
    ), patch("os.path.exists", return_value=True), patch(
        "test_gap.check_coverage_gaps",
        return_value=[
            {
                "file": "x.py",
                "uncovered_lines": [],
                "total_changed": 1,
                "covered_changed": 1,
                "coverage_pct": 100.0,
            }
        ],
    ):
        with pytest.raises(SystemExit) as exc:
            test_gap_main()
        assert exc.value.code == 0
