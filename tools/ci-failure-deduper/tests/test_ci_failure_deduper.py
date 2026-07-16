import sys
from unittest.mock import mock_open, patch

import pytest

# Insert parent dir to PATH to support folder-based import
sys.path.insert(0, "tools/ci-failure-deduper")

# pylint: disable=wrong-import-position
from ci_failure_deduper import (  # noqa: E402
    extract_failures_from_log,
    extract_python_traceback,
    group_failures,
    print_report,
    sanitize_message,
)

SAMPLE_TRACEBACK = """Some build info log
Traceback (most recent call last):
  File "main.py", line 45, in main
    do_something()
  File "utils.py", line 12, in do_something
    raise ValueError("Invalid address 0x7f12bc34ae8f")
ValueError: Invalid address 0x7f12bc34ae8f
More build info log
"""

SAMPLE_PYTEST_FAIL = """
____________________ test_division_by_zero ____________________
def test_division_by_zero():
>       assert 1 / 0 == 1
E       ZeroDivisionError: division by zero
tests/test_math.py:5: ZeroDivisionError
==================== 1 failed in 0.12s ====================
"""

SAMPLE_LINTER_ERROR = "checkers/linter.py:15:3: error: missing type annotation"
SAMPLE_GENERIC_ERROR = (
    "[2026-07-16 09:00:00] ERROR: DB Connection failed at 192.168.1.1"
)


def test_sanitize_message() -> None:
    """Test sanitization of dynamic fields in error messages."""
    msg = (
        "Error at 0x7f12bc34ae8f in /home/user/app/main.py:45:10 - elapsed time: 15.4s"
    )
    sanitized = sanitize_message(msg)
    assert "<hex_addr>" in sanitized
    assert "<path>" in sanitized
    assert "<line>:<col>" in sanitized
    assert "<duration>" in sanitized

    # Check timestamp and temp directories
    msg2 = (
        "Trace in /tmp/pytest-of-user/pytest-0/test_run - occurred 2026-07-16T12:00:00"
    )
    sanitized2 = sanitize_message(msg2)
    assert "<pytest_tempdir>" in sanitized2
    assert "<timestamp>" in sanitized2


def test_extract_python_traceback() -> None:
    """Test extracting a multiline Python traceback block."""
    lines = SAMPLE_TRACEBACK.strip().split("\n")
    tb, next_idx = extract_python_traceback(lines, 1)
    assert "Traceback (most recent call last):" in tb
    assert "ValueError: Invalid address" in tb
    assert next_idx == 7


def test_extract_failures_from_log_traceback() -> None:
    """Test failure extraction for python traceback logs."""
    m = mock_open(read_data=SAMPLE_TRACEBACK)
    with patch("builtins.open", m), patch("os.path.exists", return_value=True):
        fails = extract_failures_from_log("log.txt")
        assert len(fails) == 1
        assert fails[0][1] == "Python Traceback"
        assert "ValueError" in fails[0][0]


def test_extract_failures_from_log_pytest() -> None:
    """Test failure extraction for pytest failure logs."""
    m = mock_open(read_data=SAMPLE_PYTEST_FAIL)
    with patch("builtins.open", m), patch("os.path.exists", return_value=True):
        fails = extract_failures_from_log("log.txt")
        assert len(fails) == 1
        assert fails[0][1] == "Pytest Failure"
        assert "test_division_by_zero" in fails[0][0]


def test_extract_failures_from_log_other() -> None:
    """Test failure extraction for linter and generic errors."""
    m = mock_open(
        read_data=f"{SAMPLE_LINTER_ERROR}\n{SAMPLE_GENERIC_ERROR}\nINFO: Success"
    )
    with patch("builtins.open", m), patch("os.path.exists", return_value=True):
        fails = extract_failures_from_log("log.txt")
        # should find the linter error and the generic error, but not the INFO message
        assert len(fails) == 2
        types = [f[1] for f in fails]
        assert "Linter/Compiler Error" in types
        assert "Generic Error Log" in types


def test_group_failures() -> None:
    """Test grouping of failures across multiple log files."""
    log1_content = SAMPLE_TRACEBACK
    log2_content = SAMPLE_TRACEBACK.replace("utils.py", "other_utils.py")

    with patch("os.path.exists", return_value=True), patch(
        "builtins.open",
        side_effect=[
            mock_open(read_data=log1_content)(),
            mock_open(read_data=log2_content)(),
        ],
    ):
        groups = group_failures(["log1.txt", "log2.txt"])
        # Both tracebacks, after sanitizing their paths,
        # should resolve to the same template
        assert len(groups) == 1
        key = list(groups.keys())[0]
        assert groups[key]["count"] == 2
        assert groups[key]["files"] == {"log1.txt", "log2.txt"}


def test_print_report(capsys: pytest.CaptureFixture[str]) -> None:
    """Test printing reports in text and markdown formats."""
    groups = {
        "Template error message": {
            "template": "Template error message",
            "type": "Python Traceback",
            "count": 5,
            "files": {"job1.log", "job2.log"},
            "raw_examples": ["Raw Exception trace here"],
        }
    }

    # Text format
    print_report(groups, "text")
    captured = capsys.readouterr()
    assert "CI FAILURE DEDUPLICATION REPORT" in captured.out
    assert "Occurrences: 5" in captured.out

    # Markdown format
    print_report(groups, "markdown")
    captured = capsys.readouterr()
    assert "# CI Failure Deduplication Report" in captured.out
    assert "Root Cause 1" in captured.out
