"""Unit tests for env-diff utility."""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

# Insert parent dir to PATH to support folder-based import
sys.path.insert(0, "checkers/env-diff")

# pylint: disable=import-error,wrong-import-position
from env_diff import (  # noqa: E402
    EnvDiff,
    capture_snapshot,
    is_privileged,
    main,
    render_diff,
    sanitize_env,
)


def test_sanitize_env() -> None:
    """Test sanitizing environment variables with credentials."""
    raw = {
        "PATH": "/usr/bin",
        "API_KEY": "supersecret123",
        "DB_PASS": "pass123",
        "LOG_LEVEL": "DEBUG",
    }
    sanitized = sanitize_env(raw)
    assert sanitized["PATH"] == "/usr/bin"
    assert sanitized["API_KEY"] == "[SANITIZED]"
    assert sanitized["DB_PASS"] == "[SANITIZED]"
    assert sanitized["LOG_LEVEL"] == "DEBUG"


def test_is_privileged() -> None:
    """Test administrative privilege identification functions."""
    # Test Windows check
    with patch("sys.platform", "win32"), patch(
        "ctypes.windll.shell32.IsUserAnAdmin", create=True
    ) as mock_admin:
        mock_admin.return_value = 1
        assert is_privileged() is True

    # Test Unix check
    with patch("sys.platform", "linux"), patch("os.getuid", create=True) as mock_getuid:
        mock_getuid.return_value = 0
        assert is_privileged() is True

        mock_getuid.return_value = 1000
        assert is_privileged() is False


def test_capture_snapshot() -> None:
    """Test capturing local system context metadata."""
    snap = capture_snapshot()
    assert "os" in snap
    assert "python" in snap
    assert "env" in snap
    assert "packages" in snap
    assert "binaries" in snap
    assert "privileged" in snap


def test_env_diff_compare() -> None:
    """Test computing differences between environment profiles."""
    working = {
        "os": {"system": "Windows", "machine": "AMD64"},
        "python": {"version": "3.12.0"},
        "env": {"DEBUG": "true", "API_KEY": "[SANITIZED]"},
        "packages": {"requests": "2.31.0", "pytest": "8.0.0"},
        "binaries": {"docker": "/bin/docker", "node": "/bin/node"},
        "privileged": False,
    }

    failing = {
        "os": {"system": "Linux", "machine": "x86_64"},
        "python": {"version": "3.10.0"},
        "env": {"DEBUG": "false"},  # API_KEY is missing
        "packages": {
            "requests": "2.28.0"
        },  # pytest is missing, requests version mismatch
        "binaries": {"docker": None, "node": "/bin/node"},  # docker is missing
        "privileged": True,  # privilege mismatch
    }

    differ = EnvDiff(working, failing)
    diffs = differ.compare()

    assert diffs["os_mismatch"]["system"] == {
        "working": "Windows",
        "failing": "Linux",
    }
    assert diffs["python_mismatch"]["version"] == {
        "working": "3.12.0",
        "failing": "3.10.0",
    }
    assert "pytest" in diffs["missing_packages"]
    assert diffs["package_version_mismatches"]["requests"] == {
        "working": "2.31.0",
        "failing": "2.28.0",
    }
    assert "docker" in diffs["missing_binaries"]
    assert "API_KEY" in diffs["missing_env_vars"]
    assert diffs["env_var_mismatches"]["DEBUG"] == {
        "working": "true",
        "failing": "false",
    }
    assert diffs["privilege_mismatch"] == {"working": False, "failing": True}


def test_render_diff(capsys: pytest.CaptureFixture[str]) -> None:
    """Test generating printable reports with recommendations."""
    diffs = {
        "os_mismatch": {
            "system": {"working": "Windows", "failing": "Linux"},
        },
        "python_mismatch": {
            "version": {"working": "3.12.0", "failing": "3.10.0"},
        },
        "missing_packages": ["pytest"],
        "package_version_mismatches": {
            "requests": {"working": "2.31.0", "failing": "2.28.0"},
        },
        "missing_binaries": ["docker"],
        "missing_env_vars": ["API_KEY"],
        "env_var_mismatches": {
            "DEBUG": {"working": "true", "failing": "false"},
        },
        "privilege_mismatch": {"working": False, "failing": True},
    }

    render_diff(diffs)
    captured = capsys.readouterr()
    assert "ENVIRONMENT DIFF REPORT" in captured.out
    assert "Missing Python Packages" in captured.out
    assert "Remediation Explanations" in captured.out
    assert "pip install" in captured.out


def test_render_diff_empty(capsys: pytest.CaptureFixture[str]) -> None:
    """Test rendering report when no differences are found."""
    diffs = {
        "os_mismatch": {},
        "python_mismatch": {},
        "missing_packages": [],
        "package_version_mismatches": {},
        "missing_binaries": [],
        "missing_env_vars": [],
        "env_var_mismatches": {},
        "privilege_mismatch": None,
    }
    render_diff(diffs)
    captured = capsys.readouterr()
    assert "No critical environment discrepancies detected." in captured.out


@patch("env_diff.capture_snapshot")
def test_main_snapshot(mock_snap: MagicMock, tmp_path: pytest.TempPathFactory) -> None:
    """Test CLI snapshot capture command."""
    mock_snap.return_value = {"os": "mock"}
    output_file = tmp_path / "snapshot.json"  # type: ignore[operator]

    with patch("sys.argv", ["env-diff", "snapshot", str(output_file)]):
        main()

    with open(output_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["os"] == "mock"


def test_main_compare(tmp_path: pytest.TempPathFactory) -> None:
    """Test CLI snapshot files comparison command."""
    w_file = tmp_path / "w.json"  # type: ignore[operator]
    f_file = tmp_path / "f.json"  # type: ignore[operator]

    with open(w_file, "w", encoding="utf-8") as f:
        json.dump({"os": {"system": "Windows"}}, f)
    with open(f_file, "w", encoding="utf-8") as f:
        json.dump({"os": {"system": "Linux"}}, f)

    with patch("sys.argv", ["env-diff", "compare", str(w_file), str(f_file)]):
        main()


@patch("env_diff.capture_snapshot")
def test_main_auto(mock_snap: MagicMock, tmp_path: pytest.TempPathFactory) -> None:
    """Test CLI auto comparison command against working reference snapshot."""
    w_file = tmp_path / "w.json"  # type: ignore[operator]
    with open(w_file, "w", encoding="utf-8") as f:
        json.dump({"os": {"system": "Windows"}}, f)

    mock_snap.return_value = {"os": {"system": "Linux"}}

    with patch("sys.argv", ["env-diff", "auto", str(w_file)]):
        main()
