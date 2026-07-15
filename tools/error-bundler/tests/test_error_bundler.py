"""Unit tests for error-bundler utility."""

import json
import os
import sys
import tempfile
import zipfile
from unittest.mock import MagicMock, patch

import pytest

# Insert parent dir to PATH to support folder-based import
sys.path.insert(0, "tools/error-bundler")

# pylint: disable=import-error,wrong-import-position
from error_bundler import (  # noqa: E402
    ErrorBundler,
    collect_recent_files,
    get_installed_packages,
    get_system_diagnostics,
    main,
    sanitize_text_content,
    sanitize_value,
)


def test_sanitize_value() -> None:
    """Test environment variable masking of sensitive keys."""
    assert (
        sanitize_value("DATABASE_URL", "mysql://root:pass@localhost") == "[SANITIZED]"
    )
    assert sanitize_value("AWS_SECRET_ACCESS_KEY", "secret-key") == "[SANITIZED]"
    assert sanitize_value("PATH", "/usr/bin:/bin") == "/usr/bin:/bin"
    assert sanitize_value("PORT", "8080") == "8080"


def test_sanitize_text_content() -> None:
    """Test sanitizing assignment variables in configuration text."""
    raw_content = (
        "DEBUG=True\n"
        "DATABASE_URL=mysql://root:pass@localhost\n"
        "AWS_SECRET: super-secret-token\n"
        "PORT=80\n"
    )
    expected = (
        "DEBUG=True\n" "DATABASE_URL=[SANITIZED]\n" "AWS_SECRET:[SANITIZED]\n" "PORT=80"
    )
    assert sanitize_text_content(raw_content) == expected


def test_get_system_diagnostics() -> None:
    """Test retrieving platform/OS metadata."""
    diag = get_system_diagnostics()
    assert "os_name" in diag
    assert "platform" in diag
    assert "python_version" in diag


@patch("importlib.metadata.distributions")
def test_get_installed_packages(mock_dists: MagicMock) -> None:
    """Test mapping active packages."""
    mock_dist = MagicMock()
    mock_dist.metadata = {"Name": "pytest"}
    mock_dist.version = "8.2.2"
    mock_dists.return_value = [mock_dist]

    pkgs = get_installed_packages()
    assert pkgs["pytest"] == "8.2.2"


def test_collect_recent_files() -> None:
    """Test scanning directory with glob patterns."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create temp logs/configs
        log_file = os.path.join(temp_dir, "test.log")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("Log contents")

        pyproject = os.path.join(temp_dir, "pyproject.toml")
        with open(pyproject, "w", encoding="utf-8") as f:
            f.write("[tool.poetry]")

        files = collect_recent_files(temp_dir, ["*.log", "pyproject.toml"])
        assert sorted(files) == sorted([log_file, pyproject])


@patch("subprocess.run")
def test_error_bundler_run_and_diagnose(mock_run: MagicMock) -> None:
    """Test executing command and capturing status/outputs."""
    mock_res = MagicMock()
    mock_res.stdout = "Command output"
    mock_res.stderr = "Traceback error"
    mock_res.returncode = 1
    mock_run.return_value = mock_res

    bundler = ErrorBundler(command="python error.py")
    diag = bundler.run_and_diagnose()

    assert diag["exit_code"] == 1
    assert diag["stdout"] == "Command output"
    assert diag["stderr"] == "Traceback error"
    assert diag["duration"] >= 0.0


def test_error_bundler_bundle() -> None:
    """Test full bundle ZIP generation with correct files and sanitization."""
    with tempfile.TemporaryDirectory() as temp_dir:
        output_zip = os.path.join(temp_dir, "bundle.zip")

        # Mock target run
        bundler = ErrorBundler(stderr_input="Mock traceback stderr")

        with patch("error_bundler.collect_recent_files") as mock_files:
            mock_files.return_value = []
            bundle_path = bundler.bundle(output_zip, ["*.log"])

            assert os.path.exists(bundle_path)
            assert zipfile.is_zipfile(bundle_path)

            with zipfile.ZipFile(bundle_path, "r") as zf:
                # Check file files inside ZIP
                assert "manifest.json" in zf.namelist()
                assert "stdout.log" in zf.namelist()
                assert "stderr.log" in zf.namelist()

                # Verify manifest format
                manifest = json.loads(zf.read("manifest.json"))
                assert manifest["exit_code"] == 1
                assert manifest["system"]["python_version"] is not None


@patch("error_bundler.ErrorBundler.bundle")
def test_main_cli(mock_bundle: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI arguments and main entrypoint flow."""
    mock_bundle.return_value = "/absolute/path/to/error_bundle.zip"

    with patch("sys.argv", ["error-bundler", "-c", "python error.py"]):
        main()
        captured = capsys.readouterr()
        assert "Bundle successfully created:" in captured.out
