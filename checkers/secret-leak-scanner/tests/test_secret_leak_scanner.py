"""Unit tests for secret_leak_scanner.py."""

import argparse

# Add import injection to resolve checkers package
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pylint: disable=import-error, wrong-import-position
import secret_leak_scanner  # noqa: E402


def test_calculate_entropy() -> None:
    """Test Shannon entropy calculation."""
    assert secret_leak_scanner.calculate_entropy("") == 0.0
    # Homogeneous string has 0 entropy
    assert secret_leak_scanner.calculate_entropy("aaaaa") == 0.0
    # High entropy string
    ent1 = secret_leak_scanner.calculate_entropy("abcde")
    ent2 = secret_leak_scanner.calculate_entropy("a1B9!xQp")
    assert ent2 > ent1


def test_is_placeholder() -> None:
    """Test placeholder validation."""
    assert secret_leak_scanner.is_placeholder("my_api_key_placeholder") is True
    assert secret_leak_scanner.is_placeholder("dummy_value") is True
    assert secret_leak_scanner.is_placeholder("actualSecret_12345!A") is False


def test_mask_secret() -> None:
    """Test secret masking helper."""
    assert secret_leak_scanner.mask_secret("123") == "***"
    assert secret_leak_scanner.mask_secret("abcdefghij") == "abc...hij"


def test_scan_text() -> None:
    """Test scanning texts for signatures and generic keys."""
    # 1. AWS and GCP API keys
    gcp_line = 'API_KEY = "AIzaSyD-something_random_key_1234567890"'
    findings = secret_leak_scanner.scan_text(gcp_line, "test.txt", 4.0)
    assert len(findings) == 2  # One GCP and one generic match
    assert any(f["type"] == "Google Cloud/Firebase API Key" for f in findings)

    # 2. Slack and SSH keys
    slack_line = "token: xoxb-123456789012-abcdefghijklmnopqrstuvwx"
    findings_slack = secret_leak_scanner.scan_text(slack_line, "test.txt", 4.0)
    assert len(findings_slack) >= 1

    # 3. Check placeholder ignore
    placeholder_line = "api_key = 'your_api_key_here'"
    assert len(secret_leak_scanner.scan_text(placeholder_line, "test.txt", 4.0)) == 0


def test_find_files_recursively(tmp_path: Path) -> None:
    """Test directory crawler with exclusions."""
    d1 = tmp_path / "dir1"
    d1.mkdir()
    (d1 / "file1.py").write_text("print('hello')")
    (d1 / "secret.env").write_text("API_KEY=123")

    d2 = tmp_path / ".git"
    d2.mkdir()
    (d2 / "config").write_text("some git config")

    files = list(secret_leak_scanner.find_files_recursively(tmp_path, [r"\.git/"]))
    assert len(files) == 2
    assert any(f.name == "file1.py" for f in files)
    assert any(f.name == "secret.env" for f in files)
    assert not any(f.name == "config" for f in files)


@patch("subprocess.run")
def test_get_git_staged_files(mock_run: MagicMock) -> None:
    """Test git staged files parsing."""
    mock_run.return_value = MagicMock(
        stdout="file1.py\ncheckers/secret-leak-scanner/secret_leak_scanner.py\n",
        returncode=0,
    )
    files = secret_leak_scanner.get_git_staged_files()
    assert len(files) == 2
    assert "file1.py" in files


@patch("subprocess.run")
def test_get_git_staged_diff(mock_run: MagicMock) -> None:
    """Test git staged diff parsing."""
    mock_run.return_value = MagicMock(
        stdout="""diff --git a/file.py b/file.py
index 123..456 100644
--- a/file.py
+++ b/file.py
@@ -1,2 +1,3 @@
-old line
+added_api_key = "AIzaSyD-something_random_key_12345"
+another_line
""",
        returncode=0,
    )
    diff = secret_leak_scanner.get_git_staged_diff("file.py")
    assert "added_api_key" in diff
    assert "old line" not in diff


@patch("secret_leak_scanner.get_git_staged_files")
@patch("secret_leak_scanner.get_git_staged_diff")
def test_main_git_staged(mock_diff: MagicMock, mock_files: MagicMock) -> None:
    """Test main function with git-staged flags."""
    mock_files.return_value = ["staged.py"]
    mock_diff.return_value = 'api_key = "AIzaSyD-something_random_key_1234567890"'

    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(
            paths=[],
            git_staged=True,
            pre_commit=False,
            entropy_threshold=4.5,
            exclude=[],
        ),
    ), patch("os.path.exists", return_value=True):
        with pytest.raises(SystemExit) as exc:
            secret_leak_scanner.main()
        assert exc.value.code == 1


def test_main_paths(tmp_path: Path) -> None:
    """Test main function scanning explicit files."""
    f1 = tmp_path / "safe.py"
    f1.write_text("print('all safe here')")

    with patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(
            paths=[str(f1)],
            git_staged=False,
            pre_commit=False,
            entropy_threshold=4.5,
            exclude=[],
        ),
    ):
        with pytest.raises(SystemExit) as exc:
            secret_leak_scanner.main()
        assert exc.value.code == 0
