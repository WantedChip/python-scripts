"""Unit tests for works_on_my_machine.py."""

import ast
import importlib.metadata
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add import injection to resolve checkers package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pylint: disable=import-error, wrong-import-position
import works_on_my_machine  # noqa: E402


def test_check_python_version(tmp_path: Path) -> None:
    """Test Python version checks against project files."""
    # Test .python-version file mismatch
    python_ver_file = tmp_path / ".python-version"
    python_ver_file.write_text("9.9.9", encoding="utf-8")

    findings = works_on_my_machine.check_python_version(tmp_path)
    assert any("Python version mismatch" in f for f in findings)

    # Test pyproject.toml constraints
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('requires-python = ">=9.9.0"', encoding="utf-8")
    python_ver_file.unlink()  # remove it so we only check pyproject

    findings = works_on_my_machine.check_python_version(tmp_path)
    assert any("Python version constraint unsatisfied" in f for f in findings)


def test_evaluate_version_constraint() -> None:
    """Test helper version constraint comparisons."""
    # Test valid comparisons
    assert not works_on_my_machine.evaluate_version_constraint(">=3.8", "3.10")
    # Test invalid comparisons
    findings = works_on_my_machine.evaluate_version_constraint(">=3.12", "3.8")
    assert len(findings) == 1
    assert "unsatisfied" in findings[0]


def test_check_os_assumptions() -> None:
    """Test OS-specific imports and absolute path auditing."""
    code = """
import winreg
from termios import tcsetattr

path_win = "D:\\\\Project\\\\file.txt"
path_unix = "/usr/local/bin"
"""
    tree = works_on_my_machine.ast.parse(code)
    findings = works_on_my_machine.check_os_assumptions(tree)

    assert any("winreg" in f for f in findings)
    assert any("termios" in f for f in findings)
    assert any("D:\\" in f for f in findings)
    assert any("/usr/" in f for f in findings)


def test_check_missing_env_vars() -> None:
    """Test detection of env vars that are used but not defined."""
    code = """
import os
val1 = os.getenv("REQUIRED_API_KEY_12345")
val2 = os.environ.get("DB_PORT_XYZ")
val3 = os.environ["HOST_IP_ABC"]
"""
    tree = works_on_my_machine.ast.parse(code)

    with patch.dict("os.environ", {}):
        findings = works_on_my_machine.check_missing_env_vars(tree)
        assert len(findings) == 3
        assert any("REQUIRED_API_KEY_12345" in f for f in findings)
        assert any("DB_PORT_XYZ" in f for f in findings)
        assert any("HOST_IP_ABC" in f for f in findings)


@patch("shutil.which")
def test_check_missing_binaries(mock_which: MagicMock) -> None:
    """Test checks for external command line binaries."""
    code = """
import subprocess
import os

subprocess.run(["docker", "ps"])
os.system("ffmpeg -i input.mp4")
"""
    tree = works_on_my_machine.ast.parse(code)

    # Mock shutil.which to say docker and ffmpeg are missing
    mock_which.return_value = None
    findings = works_on_my_machine.check_missing_binaries(tree)

    assert len(findings) == 2
    assert any("docker" in f for f in findings)
    assert any("ffmpeg" in f for f in findings)


@patch("socket.socket")
def test_check_ports(mock_socket: MagicMock) -> None:
    """Test socket binding audits to detect occupied ports."""
    code = """
PORT = 8080
CONN_PORT = 9000
"""
    tree = works_on_my_machine.ast.parse(code)

    # Mock bind to raise OSError (meaning ports are in use)
    mock_sock_inst = MagicMock()
    mock_sock_inst.bind.side_effect = OSError("Address already in use")
    mock_socket.return_value = mock_sock_inst

    findings = works_on_my_machine.check_ports(tree)
    assert len(findings) == 2
    assert any("8080" in f for f in findings)
    assert any("9000" in f for f in findings)


def test_check_package_versions(tmp_path: Path) -> None:
    """Test package version checks from requirements file."""
    # Write requirements file requesting numpy version 99.9.9
    reqs = tmp_path / "requirements.txt"
    reqs.write_text("numpy==99.9.9\nnon_existent_pkg==1.0.0", encoding="utf-8")

    def mock_version(pkg: str) -> str:
        if pkg == "numpy":
            return "1.21.0"
        raise importlib.metadata.PackageNotFoundError()

    with patch("importlib.metadata.version", side_effect=mock_version):
        findings = works_on_my_machine.check_package_versions(tmp_path)

        assert any("numpy" in f and "version mismatch" in f for f in findings)
        assert any("non_existent_pkg" in f and "not installed" in f for f in findings)


def test_check_undeclared_dependencies(tmp_path: Path) -> None:
    """Test imports in code are checked against declared requirements."""
    code = """
import requests
import os
import my_local_module
"""
    tree = works_on_my_machine.ast.parse(code)

    # requirements.txt does not have requests declared
    reqs = tmp_path / "requirements.txt"
    reqs.write_text("numpy==1.21.0\n", encoding="utf-8")

    with patch("importlib.util.find_spec") as mock_spec:
        # Mock requests to look like a third-party site-packages module
        mock_spec_inst = MagicMock()
        mock_spec_inst.origin = "/path/to/site-packages/requests/__init__.py"
        mock_spec.return_value = mock_spec_inst

        findings = works_on_my_machine.check_undeclared_dependencies(tree, tmp_path)
        assert any("requests" in f and "not declared" in f for f in findings)


def test_scan_directory_ast(tmp_path: Path) -> None:
    """Test recursive directory parsing into a single AST."""
    code1 = "import sys\n"
    code2 = "import os\n"

    file1 = tmp_path / "src.py"
    file1.write_text(code1, encoding="utf-8")

    sub_dir = tmp_path / "subdir"
    sub_dir.mkdir()
    file2 = sub_dir / "helper.py"
    file2.write_text(code2, encoding="utf-8")

    tree = works_on_my_machine.scan_directory_ast(tmp_path)
    assert tree is not None
    # Verify imports from both files exist in the merged AST
    assert any(
        isinstance(node, ast.Import) and node.names[0].name == "sys"
        for node in ast.walk(tree)
    )
    assert any(
        isinstance(node, ast.Import) and node.names[0].name == "os"
        for node in ast.walk(tree)
    )


def test_cli_success(tmp_path: Path) -> None:
    """Test successful CLI run with clean environment."""
    file = tmp_path / "src.py"
    file.write_text("import sys\n", encoding="utf-8")

    args = ["works_on_my_machine.py", str(tmp_path)]
    with patch("sys.argv", args):
        with pytest.raises(SystemExit) as exc:
            works_on_my_machine.main()
        assert exc.value.code == 0


def test_cli_failure(tmp_path: Path) -> None:
    """Test CLI exit with code 1 if issues exist."""
    file = tmp_path / "src.py"
    # winreg import is platform-specific
    file.write_text("import winreg\n", encoding="utf-8")

    args = ["works_on_my_machine.py", str(tmp_path)]
    with patch("sys.argv", args):
        with pytest.raises(SystemExit) as exc:
            works_on_my_machine.main()
        assert exc.value.code == 1


def test_cli_invalid_directory() -> None:
    """Test CLI handles invalid directory arguments."""
    args = ["works_on_my_machine.py", "non_existent_directory"]
    with patch("sys.argv", args):
        with pytest.raises(SystemExit) as exc:
            works_on_my_machine.main()
        assert exc.value.code == 1
