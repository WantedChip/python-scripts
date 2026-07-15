"""Unit tests for pip-why utility."""

import json
import sys
from typing import List, Optional
from unittest.mock import MagicMock, patch

import pytest

# Insert parent dir to PATH to support folder-based import
sys.path.insert(0, "checkers/pip-why")

# pylint: disable=import-error,wrong-import-position
from pip_why import (  # noqa: E402
    DependencyGraph,
    main,
    match_constraint,
    normalize_name,
    parse_requirement,
    parse_specifiers,
    parse_version,
)


class MockDistribution:
    """Mock class representing importlib.metadata.Distribution."""

    def __init__(
        self, name: str, version: str, requires: Optional[List[str]] = None
    ) -> None:
        self.metadata = {"Name": name}
        self.version = version
        self.requires = requires or []


def test_normalize_name() -> None:
    """Test PEP 503 package name normalization."""
    assert normalize_name("Requests") == "requests"
    assert normalize_name("urllib3") == "urllib3"
    assert normalize_name("pytest-cov") == "pytest-cov"
    assert normalize_name("pytest_cov") == "pytest-cov"
    assert normalize_name("pytest.cov") == "pytest-cov"
    assert normalize_name("pytest..._---cov") == "pytest-cov"


def test_parse_requirement() -> None:
    """Test requirement string parser."""
    assert parse_requirement("requests (>=2.28.0)") == ("requests", ">=2.28.0")
    assert parse_requirement("pytest-cov>=5.0.0; extra == 'dev'") == (
        "pytest-cov",
        ">=5.0.0",
    )
    assert parse_requirement("urllib3") == ("urllib3", "")
    assert parse_requirement("invalid%req") is None


def test_parse_version() -> None:
    """Test version string parsing."""
    assert parse_version("2.28.0") == (2, 28, 0)
    assert parse_version("1.2") == (1, 2)
    assert parse_version("3.14.0.post1") == (3, 14, 0, 1)


def test_parse_specifiers() -> None:
    """Test constraint specifiers parsing."""
    assert parse_specifiers(">=2.28.0, <3.0") == [
        (">=", (2, 28, 0)),
        ("<", (3, 0)),
    ]
    assert parse_specifiers("==1.2") == [("==", (1, 2))]
    assert parse_specifiers("~=1.2.0") == [("~=", (1, 2, 0))]


def test_match_constraint() -> None:
    """Test operator constraint validation."""
    assert match_constraint((2, 28, 0), ">=", (2, 28, 0)) is True
    assert match_constraint((2, 27, 9), ">=", (2, 28, 0)) is False
    assert match_constraint((2, 28, 0), "==", (2, 28)) is True
    assert match_constraint((2, 28, 0), "!=", (2, 27)) is True
    assert match_constraint((2, 28, 0), "<", (3, 0)) is True
    assert match_constraint((2, 28, 0), "~=", (2, 28, 0)) is True
    assert match_constraint((2, 29, 0), "~=", (2, 28, 0)) is False
    assert match_constraint((2, 28, 5), "~=", (2, 28, 0)) is True
    assert match_constraint((3, 0), "~=", (2,)) is True


@patch("importlib.metadata.distributions")
def test_dependency_graph(mock_dists: MagicMock) -> None:
    """Test dependency graph mapping, path traversal, remove safety, and conflicts."""
    # Setup mock distributions
    mock_dists.return_value = [
        MockDistribution("app", "1.0.0", ["req-a", "req-b (>=2.0.0)"]),
        MockDistribution("req-a", "1.2.3", ["shared-lib"]),
        MockDistribution("req-b", "2.0.1", ["shared-lib (>=1.0.0)"]),
        MockDistribution("shared-lib", "0.9.0"),
    ]

    graph = DependencyGraph()
    graph.load_environment()

    # Verify packages loaded
    assert graph.packages["app"] == "1.0.0"
    assert graph.packages["req-a"] == "1.2.3"
    assert graph.packages["req-b"] == "2.0.1"
    assert graph.packages["shared-lib"] == "0.9.0"

    # Verify get_why_paths
    paths = graph.get_why_paths("shared-lib")
    assert sorted(paths) == [
        ["app", "req-a", "shared-lib"],
        ["app", "req-b", "shared-lib"],
    ]

    # Verify remove safety check
    is_safe, dependents = graph.check_safe_remove("shared-lib")
    assert is_safe is False
    assert sorted(dependents) == ["req-a", "req-b"]

    is_safe, dependents = graph.check_safe_remove("app")
    assert is_safe is True
    assert dependents == []

    # Verify conflict checks (shared-lib is 0.9.0 but req-b requires >=1.0.0)
    conflicts = graph.check_conflicts()
    assert len(conflicts) == 1
    assert conflicts[0][0] == "req-b"
    assert conflicts[0][2] == "shared-lib"
    assert conflicts[0][3] == "0.9.0"
    assert conflicts[0][4] == ">=1.0.0"


@patch("pip_why.DependencyGraph")
def test_main_why(
    mock_graph_cls: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test main function for the 'why' command."""
    mock_graph = mock_graph_cls.return_value
    mock_graph.packages = {"shared-lib": "1.0.0"}
    mock_graph.get_why_paths.return_value = [["app", "shared-lib"]]

    with patch("sys.argv", ["pip-why", "why", "shared-lib"]):
        main()
        captured = capsys.readouterr()
        assert "Package 'shared-lib' (version 1.0.0) is installed." in captured.out
        assert "app -> shared-lib" in captured.out


@patch("pip_why.DependencyGraph")
def test_main_why_not_installed(
    mock_graph_cls: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test main function for 'why' command with a package that is not installed."""
    mock_graph = mock_graph_cls.return_value
    mock_graph.packages = {}

    with patch("sys.argv", ["pip-why", "why", "nonexistent"]), pytest.raises(
        SystemExit
    ) as exc_info:
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Error: Package 'nonexistent' is not installed." in captured.out


@patch("pip_why.DependencyGraph")
def test_main_why_json(
    mock_graph_cls: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test main function for 'why' command with JSON output."""
    mock_graph = mock_graph_cls.return_value
    mock_graph.packages = {"shared-lib": "1.0.0"}
    mock_graph.get_why_paths.return_value = [["app", "shared-lib"]]

    with patch("sys.argv", ["pip-why", "why", "shared-lib", "--json"]):
        main()
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["package"] == "shared-lib"
        assert data["paths"] == [["app", "shared-lib"]]


@patch("pip_why.DependencyGraph")
def test_main_remove_check_safe(
    mock_graph_cls: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test main function for 'remove-check' when safe to remove."""
    mock_graph = mock_graph_cls.return_value
    mock_graph.packages = {"app": "1.0.0"}
    mock_graph.check_safe_remove.return_value = (True, [])

    with patch("sys.argv", ["pip-why", "remove-check", "app"]):
        main()
        captured = capsys.readouterr()
        assert "can be safely removed" in captured.out


@patch("pip_why.DependencyGraph")
def test_main_remove_check_unsafe(
    mock_graph_cls: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test main function for 'remove-check' when unsafe to remove."""
    mock_graph = mock_graph_cls.return_value
    mock_graph.packages = {"shared-lib": "1.0.0"}
    mock_graph.check_safe_remove.return_value = (False, ["app"])

    with patch("sys.argv", ["pip-why", "remove-check", "shared-lib"]), pytest.raises(
        SystemExit
    ) as exc_info:
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "cannot be safely removed" in captured.out
    assert "app" in captured.out


@patch("pip_why.DependencyGraph")
def test_main_remove_check_not_installed(
    mock_graph_cls: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test remove-check on a package not installed."""
    mock_graph = mock_graph_cls.return_value
    mock_graph.packages = {}

    with patch("sys.argv", ["pip-why", "remove-check", "nonexistent"]), pytest.raises(
        SystemExit
    ) as exc_info:
        main()
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "Package 'nonexistent' is not installed." in captured.out


@patch("pip_why.DependencyGraph")
def test_main_remove_check_json(
    mock_graph_cls: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test remove-check JSON output."""
    mock_graph = mock_graph_cls.return_value
    mock_graph.packages = {"app": "1.0.0"}
    mock_graph.check_safe_remove.return_value = (True, [])

    with patch("sys.argv", ["pip-why", "remove-check", "app", "--json"]):
        main()
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["package"] == "app"
        assert data["safe_to_remove"] is True


@patch("pip_why.DependencyGraph")
def test_main_conflicts_none(
    mock_graph_cls: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test conflicts subcommand with no conflicts."""
    mock_graph = mock_graph_cls.return_value
    mock_graph.check_conflicts.return_value = []

    with patch("sys.argv", ["pip-why", "conflicts"]):
        main()
        captured = capsys.readouterr()
        assert "No dependency conflicts detected" in captured.out


@patch("pip_why.DependencyGraph")
def test_main_conflicts_exist(
    mock_graph_cls: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test conflicts subcommand when conflicts exist."""
    mock_graph = mock_graph_cls.return_value
    mock_graph.check_conflicts.return_value = [
        ("req-b", "2.0.1", "shared-lib", "0.9.0", ">=1.0.0")
    ]

    with patch("sys.argv", ["pip-why", "conflicts"]), pytest.raises(
        SystemExit
    ) as exc_info:
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "version conflict(s)" in captured.out
    assert "req-b (version 2.0.1) requires shared-lib (>=1.0.0)" in captured.out


@patch("pip_why.DependencyGraph")
def test_main_conflicts_json(
    mock_graph_cls: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test conflicts subcommand with JSON output and exit code validation."""
    mock_graph = mock_graph_cls.return_value
    mock_graph.check_conflicts.return_value = [
        ("req-b", "2.0.1", "shared-lib", "0.9.0", ">=1.0.0")
    ]

    with patch("sys.argv", ["pip-why", "conflicts", "--json"]), pytest.raises(
        SystemExit
    ) as exc_info:
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert len(data) == 1
    assert data[0]["package"] == "req-b"
    assert data[0]["dependency"] == "shared-lib"
