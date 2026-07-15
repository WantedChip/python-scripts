"""Unit tests for Git Time Machine history investigation tool."""

# pylint: disable=duplicate-code,wrong-import-position,line-too-long

import os
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add current folder to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# pylint: disable=import-error
from git_time_machine import (  # noqa: E402
    find_config_change,
    find_dependency_introduction,
    find_file_growth,
    format_bytes,
    general_search,
    main,
    parse_commit_diffs,
    parse_size,
    run_git,
)


def test_run_git_success() -> None:
    """Tests run_git returns output on successful command execution."""
    with patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "git-output\n"
        mock_run.return_value = mock_res

        out = run_git(["status"])
        assert out == "git-output\n"
        mock_run.assert_called_once_with(
            ["git", "status"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )


def test_run_git_failure() -> None:
    """Tests run_git raises RuntimeError on command failures."""
    with patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 128
        mock_res.stderr = "fatal: not a git repository"
        mock_run.return_value = mock_res

        with pytest.raises(RuntimeError) as exc_info:
            run_git(["status"])
        assert "not a git repository" in str(exc_info.value)

        # Test OSError/FileNotFoundError
        mock_run.side_effect = FileNotFoundError()
        with pytest.raises(RuntimeError) as exc_info_err:
            run_git(["status"])
        assert "failed" in str(exc_info_err.value)


def test_parse_commit_diffs() -> None:
    """Tests parsing raw Git log patch outputs into structured records."""
    mock_log = (
        "commit 1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b\n"
        "Author: Alice <alice@example.com>\n"
        "Date:   Wed Jul 15 12:00:00 2026 +0000\n"
        "\n"
        "    Add database password config option\n"
        "\n"
        "diff --git a/.env b/.env\n"
        "--- a/.env\n"
        "+++ b/.env\n"
        "+DB_PASSWORD=secret_pass\n"
        "-DB_PASSWORD=old_pass\n"
    )

    commits = parse_commit_diffs(mock_log)
    assert len(commits) == 1
    commit = commits[0]
    assert commit["hash"] == "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b"
    assert commit["author"] == "Alice <alice@example.com>"
    assert commit["date"] == "Wed Jul 15 12:00:00 2026 +0000"
    assert commit["message"] == "Add database password config option"
    assert "DB_PASSWORD=secret_pass" in commit["diff"]
    assert "DB_PASSWORD=old_pass" in commit["diff"]


def test_parse_size() -> None:
    """Tests parsing of human-readable sizes into bytes."""
    assert parse_size("500") == 500
    assert parse_size("1KB") == 1024
    assert parse_size("2MB") == 2097152
    assert parse_size("1.5M") == 1572864
    assert parse_size("1GB") == 1073741824

    with pytest.raises(ValueError):
        parse_size("invalid")

    with pytest.raises(ValueError):
        parse_size("100TB")  # Unknown unit


def test_format_bytes() -> None:
    """Tests formatting bytes counts into human-readable strings."""
    assert format_bytes(500) == "500.00 B"
    assert format_bytes(2048) == "2.00 KB"
    assert format_bytes(1048576 * 3) == "3.00 MB"


def test_find_config_change() -> None:
    """Tests searching config changes in history logs."""
    mock_log = (
        "commit 1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b\n"
        "Author: Alice\n"
        "Date:   Wed Jul 15 12:00:00 2026\n"
        "\n"
        "    Change database URL\n"
        "\n"
        "+DATABASE_URL=postgres://localhost\n"
    )

    with patch("git_time_machine.run_git", return_value=mock_log) as mock_run:
        find_config_change("DATABASE_URL", ".env")
        mock_run.assert_called_once_with(["log", "-p", "-GDATABASE_URL", "--", ".env"])


def test_find_dependency_introduction() -> None:
    """Tests identifying when a dependency package was introduced."""
    mock_log = (
        "commit 9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e\n"
        "Author: Bob\n"
        "Date:   Tue Jul 14 10:00:00 2026\n"
        "\n"
        "    Add django dependency\n"
        "\n"
        "+Django==4.2.3\n"
    )

    def mock_run_git(args: list[str]) -> str:
        if "log" in args:
            return mock_log
        return ""

    with patch("git_time_machine.run_git", side_effect=mock_run_git):
        # Specifying file path directly
        find_dependency_introduction("Django", "requirements.txt")


def test_find_file_growth() -> None:
    """Tests file size tracking logic over historical commits."""
    mock_log = (
        "1a2b3c4d|Wed Jul 15|Add small file\n"
        "5f6g7h8i|Wed Jul 15|Add lots of assets\n"
    )

    def mock_run_git(args: list[str]) -> str:
        if "--reverse" in args:
            return mock_log
        if "cat-file" in args:
            # First commit size is 100 bytes, second is 2MB
            if "1a2b3c4d" in args[2]:
                return "100"
            if "5f6g7h8i" in args[2]:
                return "2097152"
        return ""

    with patch("git_time_machine.run_git", side_effect=mock_run_git):
        find_file_growth("assets.zip", "1MB")


def test_find_file_growth_never_exceeded() -> None:
    """Tests file size tracking when threshold is never exceeded."""
    mock_log = "1a2b3c4d|Wed Jul 15|Add small file\n"

    def mock_run_git(args: list[str]) -> str:
        if "--reverse" in args:
            return mock_log
        if "cat-file" in args:
            return "100"
        return ""

    with patch("git_time_machine.run_git", side_effect=mock_run_git):
        find_file_growth("small.txt", "1MB")


def test_general_search() -> None:
    """Tests general string search across all commits."""
    mock_log = (
        "commit 1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b\n"
        "Author: Alice\n"
        "Date:   Wed Jul 15\n"
        "\n"
        "    Fix critical logic\n"
        "\n"
        "+# FIXME: temporary workaround\n"
    )

    with patch("git_time_machine.run_git", return_value=mock_log) as mock_run:
        general_search("FIXME")
        mock_run.assert_called_once_with(["log", "-p", "-SFIXME"])


def test_find_config_change_no_commits() -> None:
    """Tests find_config_change when no commits match."""
    with patch("git_time_machine.run_git", return_value="") as mock_run:
        find_config_change("DATABASE_URL", ".env")
        mock_run.assert_called_once()


def test_find_config_change_error() -> None:
    """Tests find_config_change when a RuntimeError is raised."""
    with patch("git_time_machine.run_git", side_effect=RuntimeError("git error")):
        with pytest.raises(SystemExit):
            find_config_change("DATABASE_URL", ".env")


def test_find_dependency_introduction_auto_detect() -> None:
    """Tests dependency introduction with file auto-detection."""

    def mock_run_git(run_args: list[str]) -> str:
        if "log" in run_args:
            # Simulate requirements.txt exists and has history
            if "requirements.txt" in run_args:
                return "commit hash\nAuthor: Alice\nDate: Wed Jul 15\n\n+package==1.0.0"
        return ""

    with patch("git_time_machine.run_git", side_effect=mock_run_git):
        find_dependency_introduction("package", None)


def test_find_dependency_introduction_error() -> None:
    """Tests dependency introduction handles file log error gracefully."""
    with patch("git_time_machine.run_git", side_effect=RuntimeError("git error")):
        # Should not raise SystemExit, just prints warning and continues
        find_dependency_introduction("package", "requirements.txt")


def test_find_file_growth_invalid_threshold() -> None:
    """Tests find_file_growth exits on invalid threshold format."""
    with pytest.raises(SystemExit):
        find_file_growth("file.txt", "invalid_size")


def test_find_file_growth_no_history() -> None:
    """Tests find_file_growth when file has no history."""
    with patch("git_time_machine.run_git", return_value=""):
        find_file_growth("file.txt", "1MB")


def test_find_file_growth_missing_in_commit() -> None:
    """Tests find_file_growth when file is missing in some commits."""
    mock_log = "1a2b3c4d|Wed Jul 15|Add small file\n"

    def mock_run_git(run_args: list[str]) -> str:
        if "--reverse" in run_args:
            return mock_log
        if "cat-file" in run_args:
            raise RuntimeError("File not found in commit")
        return ""

    with patch("git_time_machine.run_git", side_effect=mock_run_git):
        find_file_growth("file.txt", "1MB")


def test_find_file_growth_error() -> None:
    """Tests find_file_growth exits on git RuntimeError."""
    with patch("git_time_machine.run_git", side_effect=RuntimeError("git error")):
        with pytest.raises(SystemExit):
            find_file_growth("file.txt", "1MB")


def test_general_search_no_commits() -> None:
    """Tests general_search when no commits are found."""
    with patch("git_time_machine.run_git", return_value=""):
        general_search("FIXME")


def test_general_search_error() -> None:
    """Tests general_search exits on git RuntimeError."""
    with patch("git_time_machine.run_git", side_effect=RuntimeError("git error")):
        with pytest.raises(SystemExit):
            general_search("FIXME")


def test_main_config() -> None:
    """Tests main function parsed command executions for config."""
    test_args = ["git_time_machine.py", "config", "-p", "URL", "-f", ".env"]
    with patch("sys.argv", test_args), patch(
        "git_time_machine.find_config_change"
    ) as mock_find:
        main()
        mock_find.assert_called_once_with("URL", ".env")


def test_main_dependency() -> None:
    """Tests main function parsed command executions for dependency."""
    test_args = ["git_time_machine.py", "dependency", "-n", "Django", "-f", "reqs.txt"]
    with patch("sys.argv", test_args), patch(
        "git_time_machine.find_dependency_introduction"
    ) as mock_find:
        main()
        mock_find.assert_called_once_with("Django", "reqs.txt")


def test_main_file_size() -> None:
    """Tests main function parsed command executions for file-size."""
    test_args = ["git_time_machine.py", "file-size", "-f", "db.sqlite", "-t", "500KB"]
    with patch("sys.argv", test_args), patch(
        "git_time_machine.find_file_growth"
    ) as mock_find:
        main()
        mock_find.assert_called_once_with("db.sqlite", "500KB")


def test_main_search() -> None:
    """Tests main function parsed command executions for search."""
    test_args = ["git_time_machine.py", "search", "-q", "TODO"]
    with patch("sys.argv", test_args), patch(
        "git_time_machine.general_search"
    ) as mock_find:
        main()
        mock_find.assert_called_once_with("TODO")
