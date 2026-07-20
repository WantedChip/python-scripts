import argparse
import os
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

# Ensure target directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import secret_history_check  # noqa: E402


def test_is_git_repo_success():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        assert secret_history_check.is_git_repo("/dummy/path") is True
        mock_run.assert_called_once_with(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd="/dummy/path",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )


def test_is_git_repo_failure():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        assert secret_history_check.is_git_repo("/dummy/path") is False


def test_is_git_repo_oserror():
    with patch("subprocess.run", side_effect=OSError("git not installed")):
        assert secret_history_check.is_git_repo("/dummy/path") is False


def mock_process_with_stdout(lines_list):
    mock_proc = MagicMock()
    mock_stdout = MagicMock()
    mock_stdout.__iter__.return_value = iter(lines_list)
    mock_proc.stdout = mock_stdout
    return mock_proc


def test_scan_git_history_no_findings():
    dummy_git_log = [
        "commit a1b2c3d4e5f6g7h8i9j0\n",
        "Author: Test User <test@example.com>\n",
        "Date:   Mon Jan 1 00:00:00 2026\n",
        "diff --git a/file.txt b/file.txt\n",
        "--- a/file.txt\n",
        "+++ b/file.txt\n",
        "+This is a clean added line.\n",
        "-This is a removed line.\n",
    ]

    mock_proc = mock_process_with_stdout(dummy_git_log)

    with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
        findings = secret_history_check.scan_git_history("/dummy/path", None)
        assert findings == []
        mock_popen.assert_called_once_with(
            ["git", "log", "-p", "--all", "--unified=0"],
            cwd="/dummy/path",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
        )
        mock_proc.wait.assert_called_once()
        mock_proc.stdout.close.assert_called_once()


def test_scan_git_history_with_secrets():
    dummy_git_log = [
        "commit a1b2c3d4e5f6\n",
        "Author: Test User <test@example.com>\n",
        "Date:   Mon Jan 1 00:00:00 2026\n",
        "diff --git a/secret.py b/secret.py\n",
        "--- a/secret.py\n",
        "+++ b/secret.py\n",
        "+# Testing AWS Access Key ID\n",
        "+aws_key = AKIA1234567890ABCDEF\n",
        "+# Testing generic secret\n",
        "+password = 'my_super_secret_password_123'\n",
        "+# Testing private key header\n",
        "+-----BEGIN RSA PRIVATE KEY-----\n",
        "+# Testing GitHub Token\n",
        "+token = ghp_1234567890abcdef1234567890abcdef1234\n",
        "+# Non-matching line\n",
        "+normal_line = 'hello'\n",
    ]

    mock_proc = mock_process_with_stdout(dummy_git_log)

    with patch("subprocess.Popen", return_value=mock_proc):
        findings = secret_history_check.scan_git_history("/dummy/path", None)

        # We expect 4 findings: AWS key, Generic password, Private key, GitHub token
        assert len(findings) == 4

        # Check AWS Key finding
        assert findings[0]["leak_type"] == "AWS Access Key ID"
        assert findings[0]["commit"] == "a1b2c3d4e5f6"
        assert findings[0]["author"] == "Test User <test@example.com>"
        assert findings[0]["date"] == "Mon Jan 1 00:00:00 2026"
        assert findings[0]["file"] == "secret.py"
        assert "AKIA1234567890ABCDEF" in findings[0]["line"]

        # Check Generic Secret
        assert findings[1]["leak_type"] == "Generic Secret/Password Key"
        assert "password = 'my_super_secret_password_123'" in findings[1]["line"]

        # Check Private Key
        assert findings[2]["leak_type"] == "Private Key Header"

        # Check GitHub Token
        assert findings[3]["leak_type"] == "GitHub Token"


def test_scan_git_history_custom_query():
    dummy_git_log = [
        "commit a1b2c3d4e5f6\n",
        "Author: Test User <test@example.com>\n",
        "Date:   Mon Jan 1 00:00:00 2026\n",
        "diff --git a/test.py b/test.py\n",
        "--- a/test.py\n",
        "+++ b/test.py\n",
        "+my_custom_token_here = 'super_secret_value'\n",
        "+unrelated_line = 42\n",
    ]

    mock_proc = mock_process_with_stdout(dummy_git_log)

    with patch("subprocess.Popen", return_value=mock_proc):
        findings = secret_history_check.scan_git_history(
            "/dummy/path", "my_custom_token_here"
        )

        assert len(findings) == 1
        assert findings[0]["leak_type"] == "Search Query 'my_custom_token_here'"
        assert "my_custom_token_here" in findings[0]["line"]


def test_scan_git_history_exception():
    with patch("subprocess.Popen", side_effect=RuntimeError("Process failed")):
        findings = secret_history_check.scan_git_history("/dummy/path", None)
        assert findings == []


def raise_exit(code=0):
    raise SystemExit(code)


def test_main_path_not_found():
    with patch("os.path.exists", return_value=False), patch(
        "sys.exit", side_effect=raise_exit
    ), patch("argparse.ArgumentParser.parse_args") as mock_parse:

        mock_parse.return_value = argparse.Namespace(
            repo_path="/nonexistent", query=None
        )
        with pytest.raises(SystemExit) as excinfo:
            secret_history_check.main()
        assert excinfo.value.code == 1


def test_main_not_git_repository():
    with patch("os.path.exists", return_value=True), patch(
        "secret_history_check.is_git_repo", return_value=False
    ), patch("sys.exit", side_effect=raise_exit), patch(
        "argparse.ArgumentParser.parse_args"
    ) as mock_parse:

        mock_parse.return_value = argparse.Namespace(repo_path="/repo", query=None)
        with pytest.raises(SystemExit) as excinfo:
            secret_history_check.main()
        assert excinfo.value.code == 1


def test_main_no_findings():
    with patch("os.path.exists", return_value=True), patch(
        "secret_history_check.is_git_repo", return_value=True
    ), patch("secret_history_check.scan_git_history", return_value=[]), patch(
        "sys.exit", side_effect=raise_exit
    ), patch(
        "argparse.ArgumentParser.parse_args"
    ) as mock_parse:

        mock_parse.return_value = argparse.Namespace(repo_path="/repo", query=None)
        with pytest.raises(SystemExit) as excinfo:
            secret_history_check.main()
        assert excinfo.value.code == 0


def test_main_with_findings():
    findings = [
        {
            "commit": "a1b2c3d4e5f6",
            "author": "Test User",
            "date": "Mon Jan 1",
            "file": "config.json",
            "leak_type": "AWS Access Key ID",
            "line": "AKIA1234567890ABCDEF",
        },
        # Duplicate match to test deduplication logic
        {
            "commit": "a1b2c3d4e5f6",
            "author": "Test User",
            "date": "Mon Jan 1",
            "file": "config.json",
            "leak_type": "AWS Access Key ID",
            "line": "AKIA1234567890ABCDEF",
        },
    ]

    with patch("os.path.exists", return_value=True), patch(
        "secret_history_check.is_git_repo", return_value=True
    ), patch("secret_history_check.scan_git_history", return_value=findings), patch(
        "sys.exit", side_effect=raise_exit
    ) as mock_exit, patch(
        "argparse.ArgumentParser.parse_args"
    ) as mock_parse:

        mock_parse.return_value = argparse.Namespace(
            repo_path="/repo", query="some_query"
        )
        secret_history_check.main()
        mock_exit.assert_not_called()
