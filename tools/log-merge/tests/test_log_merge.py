import os
import sys
from datetime import datetime
from unittest.mock import mock_open, patch

import pytest

# Add parent directory to sys.path so we can import the script
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from log_merge import main, parse_timestamp, read_log_file  # noqa: E402


def test_parse_timestamp_valid():
    assert parse_timestamp("2026-07-16 12:34:56.789 [INFO] Log message") == datetime(
        2026, 7, 16, 12, 34, 56, 789000
    )
    assert parse_timestamp("2026-07-16T12:34:56Z [INFO] Log message") == datetime(
        2026, 7, 16, 12, 34, 56
    )
    assert parse_timestamp(
        "2026-07-16 12:34:56.789123+02:00 [INFO] Log message"
    ) == datetime(2026, 7, 16, 12, 34, 56, 789123)
    assert parse_timestamp("2026-07-16 12:34:56") == datetime(2026, 7, 16, 12, 34, 56)


def test_parse_timestamp_invalid():
    assert parse_timestamp("No timestamp here") is None


@patch("os.path.exists", return_value=False)
def test_read_log_file_not_exists(mock_exists):
    assert read_log_file("nonexistent.log") == []


@patch("os.path.exists", return_value=True)
def test_read_log_file_os_error(mock_exists):
    with patch("builtins.open", side_effect=OSError("Read error")):
        assert read_log_file("error.log") == []


@patch("os.path.exists", return_value=True)
def test_read_log_file_content(mock_exists):
    log_content = """
    First line has no timestamp and should be skipped
    2026-07-16 12:00:00 [INFO] Initializing service
    Some multi-line trace details
    2026-07-16 12:00:05 [ERROR] Connection failed

    2026-07-16 12:00:10 [FATAL] Crash occurred
    """
    with patch("builtins.open", mock_open(read_data=log_content)):
        entries = read_log_file("service.log")
        assert len(entries) == 4

        assert (
            entries[0]["content"] == "2026-07-16 12:00:00 [INFO] Initializing service"
        )
        assert entries[0]["timestamp"] == datetime(2026, 7, 16, 12, 0, 0)
        assert entries[0]["is_error"] is False
        assert entries[0]["line_number"] == 3

        assert entries[1]["content"] == "Some multi-line trace details"
        assert entries[1]["timestamp"] == datetime(2026, 7, 16, 12, 0, 0)
        assert entries[1]["is_error"] is False
        assert entries[1]["line_number"] == 4

        assert entries[2]["content"] == "2026-07-16 12:00:05 [ERROR] Connection failed"
        assert entries[2]["timestamp"] == datetime(2026, 7, 16, 12, 0, 5)
        assert entries[2]["is_error"] is True
        assert entries[2]["line_number"] == 5

        assert entries[3]["content"] == "2026-07-16 12:00:10 [FATAL] Crash occurred"
        assert entries[3]["timestamp"] == datetime(2026, 7, 16, 12, 0, 10)
        assert entries[3]["is_error"] is True
        assert entries[3]["line_number"] == 7


@patch("sys.argv", ["log_merge.py", "file1.log"])
@patch("log_merge.read_log_file", return_value=[])
@patch("sys.exit")
@patch("builtins.print")
def test_main_no_entries(mock_print, mock_exit, mock_read_log):
    mock_exit.side_effect = SystemExit
    with pytest.raises(SystemExit):
        main()
    mock_exit.assert_called_once_with(0)


@patch(
    "sys.argv",
    ["log_merge.py", "file1.log", "file2.log", "-o", "merged.log", "-p", "2"],
)
@patch("log_merge.read_log_file")
@patch("builtins.print")
def test_main_success(mock_print, mock_read_log):
    entries_file1 = [
        {
            "timestamp": datetime(2026, 7, 16, 12, 0, 0),
            "source": "file1.log",
            "line_number": 1,
            "content": "2026-07-16 12:00:00 [INFO] Start",
            "is_error": False,
        },
        {
            "timestamp": datetime(2026, 7, 16, 12, 0, 5),
            "source": "file1.log",
            "line_number": 2,
            "content": "2026-07-16 12:00:05 [INFO] Duplicate task",
            "is_error": False,
        },
        {
            "timestamp": datetime(2026, 7, 16, 12, 0, 6),
            "source": "file1.log",
            "line_number": 3,
            "content": "2026-07-16 12:00:06 [INFO] Duplicate task",
            "is_error": False,
        },
    ]

    entries_file2 = [
        {
            "timestamp": datetime(2026, 7, 16, 12, 0, 2),
            "source": "file2.log",
            "line_number": 1,
            "content": "2026-07-16 12:00:02 [INFO] File2 event",
            "is_error": False,
        },
        {
            "timestamp": datetime(2026, 7, 16, 12, 0, 10),
            "source": "file2.log",
            "line_number": 2,
            "content": "2026-07-16 12:00:10 [ERROR] Crash",
            "is_error": True,
        },
    ]

    def read_log_side_effect(filepath):
        if filepath == "file1.log":
            return entries_file1
        return entries_file2

    mock_read_log.side_effect = read_log_side_effect

    m_open = mock_open()
    with patch("builtins.open", m_open):
        main()

    m_open.assert_called_once_with(os.path.abspath("merged.log"), "w", encoding="utf-8")


@patch("sys.argv", ["log_merge.py", "file1.log", "-o", "merged.log"])
@patch("log_merge.read_log_file")
@patch("builtins.print")
def test_main_write_error(mock_print, mock_read_log):
    mock_read_log.return_value = [
        {
            "timestamp": datetime(2026, 7, 16, 12, 0, 0),
            "source": "file1.log",
            "line_number": 1,
            "content": "2026-07-16 12:00:00 [INFO] Start",
            "is_error": False,
        }
    ]
    with patch("builtins.open", side_effect=OSError("Write failed")):
        main()
