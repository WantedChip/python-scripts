"""Tests for Dependency Update Reporter."""

import json
import sys
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# pylint: disable=import-error, wrong-import-position
# pylint: disable=unused-argument, import-outside-toplevel
import dep_reporter  # noqa: E402


def test_parse_semver() -> None:
    """Test SemVer component parsing."""
    assert dep_reporter.parse_semver("1.2.3") == (1, 2, 3)
    assert dep_reporter.parse_semver("v2.10") == (2, 10, 0)
    assert dep_reporter.parse_semver("3.0.0b1") == (3, 0, 0)
    assert dep_reporter.parse_semver("invalid") == (0, 0, 0)


def test_evaluate_upgrade_risk() -> None:
    """Test upgrade risk level assignments."""
    assert "High" in dep_reporter.evaluate_upgrade_risk("1.0.0", "2.0.0")
    assert "Medium" in dep_reporter.evaluate_upgrade_risk("1.0.0", "1.1.0")
    assert "Low" in dep_reporter.evaluate_upgrade_risk("1.0.0", "1.0.1")
    assert dep_reporter.evaluate_upgrade_risk("1.0.0", "1.0.0") == "None"
    assert dep_reporter.evaluate_upgrade_risk("*", "3.1.2") == "None"


def test_parse_requirements_txt() -> None:
    """Test parsing standard pip requirements.txt format lines."""
    content = (
        "# Core dependencies\n"
        "numpy==1.26.2\n"
        "requests>=2.31.0\n"
        "pytest\n"
        "-r other.txt\n"
    )
    deps = dep_reporter.parse_requirements_txt(content)
    assert deps["numpy"] == "1.26.2"
    assert deps["requests"] == "2.31.0"
    assert deps["pytest"] == "*"


def test_parse_pyproject_toml() -> None:
    """Test parsing standard TOML dependencies fields."""
    content = """
[project]
dependencies = [
  "pypdf>=6.0.0",
  "black"
]
"""
    deps = dep_reporter.parse_pyproject_toml(content)
    assert deps["pypdf"] == "6.0.0"
    assert deps["black"] == "*"


def test_parse_pyproject_toml_poetry() -> None:
    """Test parsing Poetry-specific dependencies fields."""
    content = """
[tool.poetry.dependencies]
python = "^3.12"
pandas = "2.1.3"
pylint = { version = "3.0.2", extras = ["spelling"] }
[tool.poetry.group.dev.dependencies]
pytest = "^8.0.0"
"""
    deps = dep_reporter.parse_pyproject_toml(content)
    assert deps["pandas"] == "2.1.3"
    assert deps["pylint"] == "3.0.2"
    assert deps["pytest"] == "^8.0.0"


class MockUrlOpenResponse:
    """Mock urlopen response class."""

    def __init__(self, data: bytes, code: int = 200) -> None:
        self.data = data
        self.code = code

    def read(self) -> bytes:
        """Mock read."""
        return self.data

    def __enter__(self) -> "MockUrlOpenResponse":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        pass


def test_fetch_pypi_metadata_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test successfully fetching package info metadata."""
    dummy_payload = {
        "info": {
            "name": "numpy",
            "version": "1.26.2",
            "project_urls": {"Changelog": "https://numpy.org/doc/stable/release.html"},
        },
        "releases": {"1.26.2": [{"upload_time": "2023-11-20T12:00:00Z"}]},
    }
    dummy_bytes = json.dumps(dummy_payload).encode("utf-8")

    def mock_urlopen(*args: Any, **kwargs: Any) -> MockUrlOpenResponse:
        return MockUrlOpenResponse(dummy_bytes)

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    data = dep_reporter.fetch_pypi_metadata("numpy")
    assert data["info"]["name"] == "numpy"


def test_fetch_pypi_metadata_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test PyPI 404 response triggers value error exception."""

    def mock_urlopen_error(*args: Any, **kwargs: Any) -> None:
        fp = BytesIO(b"Not Found")
        raise HTTPError("https://pypi.org", 404, "Not Found", {}, fp)  # type: ignore

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_error)

    with pytest.raises(ValueError) as exc:
        dep_reporter.fetch_pypi_metadata("nonexistent-package")
    assert "Package not found on PyPI" in str(exc.value)


def test_scan_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test complete scanning pipeline logic."""
    dummy_payload = {
        "info": {
            "version": "2.0.0",
            "project_urls": {"Release Notes": "http://notes.com"},
        },
        "releases": {"2.0.0": [{"upload_time": "2026-07-10T12:00:00Z"}]},
    }
    dummy_bytes = json.dumps(dummy_payload).encode("utf-8")

    def mock_urlopen(*args: Any, **kwargs: Any) -> MockUrlOpenResponse:
        return MockUrlOpenResponse(dummy_bytes)

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    deps = {"requests": "1.0.0"}
    reports = dep_reporter.scan_dependencies(deps)

    assert len(reports) == 1
    assert reports[0].name == "requests"
    assert reports[0].latest_version == "2.0.0"
    assert reports[0].latest_release_date == "2026-07-10"
    assert "High" in reports[0].upgrade_risk


def test_main_cli_markdown_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test CLI output generation formats."""
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("numpy==1.0.0\n", encoding="utf-8")
    out_md = tmp_path / "out.md"

    dummy_payload = {
        "info": {"version": "1.2.0", "project_urls": {}},
        "releases": {"1.2.0": [{"upload_time": "2026-07-10T12:00:00Z"}]},
    }
    dummy_bytes = json.dumps(dummy_payload).encode("utf-8")

    import urllib.request

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *args, **kwargs: MockUrlOpenResponse(dummy_bytes),
    )

    args = [
        "dep_reporter.py",
        "-i",
        str(req_file),
        "-o",
        str(out_md),
        "--format",
        "markdown",
    ]
    monkeypatch.setattr(sys, "argv", args)
    dep_reporter.main()

    assert out_md.exists()
    assert "Dependency Update Report" in out_md.read_text(encoding="utf-8")


def test_main_cli_missing_input_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI exit codes on bad inputs."""
    args = ["dep_reporter.py", "-i", "nonexistent_reqs.txt"]
    monkeypatch.setattr(sys, "argv", args)

    with pytest.raises(SystemExit) as exc:
        dep_reporter.main()
    assert exc.value.code == 1
