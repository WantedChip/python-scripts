"""Unit tests for repo_doctor.py."""

import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pylint: disable=import-error, wrong-import-position
import repo_doctor  # noqa: E402


def test_check_readme(tmp_path: Path) -> None:
    """Test readme section header audits."""
    # 1. Missing readme
    findings = repo_doctor.check_readme(tmp_path)
    assert any("Missing README file" in f for f in findings)

    # 2. Incomplete readme headers
    readme = tmp_path / "README.md"
    readme.write_text("# My Project\nNo sections here.")
    findings = repo_doctor.check_readme(tmp_path)
    assert len(findings) == 4  # Installation, Usage, License, Requirements missing

    # 3. Complete readme
    complete_text = """
# My Project
## Installation
Run pip install.
## Usage
Run python main.py.
## Requirements
Python 3.x
## License
MIT License
"""
    readme.write_text(complete_text)
    findings = repo_doctor.check_readme(tmp_path)
    assert len(findings) == 0


def test_check_setup_files(tmp_path: Path) -> None:
    """Test syntax checking of setup.py and pyproject.toml."""
    # 1. setup.py with syntax error
    setup_py = tmp_path / "setup.py"
    setup_py.write_text("import setuptools\nsetup(")  # Mismatched bracket syntax error
    findings = repo_doctor.check_setup_files(tmp_path)
    assert any("setup.py has python syntax errors" in f for f in findings)

    # 2. setup.py valid syntax
    setup_py.write_text("import setuptools\nprint('ok')")
    findings = repo_doctor.check_setup_files(tmp_path)
    assert len(findings) == 0


@patch("urllib.request.urlopen")
def test_query_pypi_latest(mock_urlopen: MagicMock) -> None:
    """Test fetching package version information from PyPI JSON endpoint."""
    mock_response = MagicMock()
    mock_response.read.return_value = b'{"info": {"version": "2.0.0"}}'
    mock_urlopen.return_value.__enter__.return_value = mock_response

    ver = repo_doctor.query_pypi_latest("requests")
    assert ver == "2.0.0"

    # PyPI error/offline
    mock_urlopen.side_effect = Exception("Connection error")
    assert repo_doctor.query_pypi_latest("requests") is None


@patch("repo_doctor.query_pypi_latest")
def test_check_stale_dependencies(mock_query: MagicMock, tmp_path: Path) -> None:
    """Test checking pinned and unpinned dependencies."""
    req_file = tmp_path / "requirements.txt"

    # 1. No requirements file (no findings)
    assert len(repo_doctor.check_stale_dependencies(tmp_path)) == 0

    # 2. Unpinned dependency
    req_file.write_text("requests\npytest==8.2.0")
    findings = repo_doctor.check_stale_dependencies(tmp_path)
    assert any("requests' is not pinned" in f for f in findings)

    # 3. Outdated dependency
    mock_query.return_value = "8.2.2"
    findings = repo_doctor.check_stale_dependencies(tmp_path, check_pypi=True)
    assert any("Dependency 'pytest' is outdated" in f for f in findings)


def test_check_gitignore(tmp_path: Path) -> None:
    """Test gitignore pattern auditing."""
    # 1. Missing gitignore
    findings = repo_doctor.check_gitignore(tmp_path)
    assert any("Missing .gitignore" in f for f in findings)

    # 2. Incomplete gitignore
    gi = tmp_path / ".gitignore"
    gi.write_text(".vscode/")
    findings = repo_doctor.check_gitignore(tmp_path)
    assert len(findings) > 0

    # 3. Complete gitignore
    gi.write_text(".venv/\n__pycache__/\nbuild/\n.vscode/\n.coverage")
    findings = repo_doctor.check_gitignore(tmp_path)
    assert len(findings) == 0


def test_scan_file_system_issues(tmp_path: Path) -> None:
    """Test scan for giant files and accidental binaries."""
    # 1. Create a binary extension file
    bin_file = tmp_path / "accidental.exe"
    bin_file.write_text("compiled_bytes")

    # 2. Create a giant file
    giant_file = tmp_path / "giant.txt"
    # Write 2 MB content
    giant_file.write_text("a" * (2 * 1024 * 1024))

    # Run check stages with 1MB threshold limit
    giant, binaries = repo_doctor.scan_file_system_issues(tmp_path, max_size_mb=1)
    assert any("giant.txt" in f for f in giant)
    assert any("accidental.exe" in f for f in binaries)


@patch("urllib.request.urlopen")
def test_verify_url(mock_urlopen: MagicMock) -> None:
    """Test HTTP link checking status codes."""
    # 1. Accessible HEAD
    mock_response = MagicMock(status=200)
    mock_urlopen.return_value.__enter__.return_value = mock_response
    assert repo_doctor.verify_url("http://google.com") is True

    # 2. Dead link (404)
    mock_urlopen.side_effect = urllib.error.HTTPError(
        "http://bad.com", 404, "Not Found", None, None
    )
    assert repo_doctor.verify_url("http://bad.com") is False


@patch("repo_doctor.verify_url")
def test_check_dead_links(mock_verify: MagicMock, tmp_path: Path) -> None:
    """Test dead documentation link checks inside markdown documents."""
    mock_verify.side_effect = lambda url: url == "http://good.com"

    md_file = tmp_path / "docs.md"
    md_file.write_text("Check [this](http://good.com) or [that](http://broken.com)")

    findings = repo_doctor.check_dead_links(tmp_path)
    assert any("Dead link in docs.md: http://broken.com" in f for f in findings)
    assert not any("http://good.com" in f for f in findings)


def test_check_secrets(tmp_path: Path) -> None:
    """Test detecting credential leak signatures in files."""
    code_file = tmp_path / "main.py"
    code_file.write_text("aws_key = 'AKIA1234567890123456'\n")

    findings = repo_doctor.check_secrets(tmp_path)
    assert any("AWS Client Access Key" in f for f in findings)

    # Shannon high entropy token detection (a random long hash string)
    code_file.write_text("random_token = 'jX8rP3s9Fv2zQ1yK5wT0xM7bN4qC6hL9aU'\n")
    findings = repo_doctor.check_secrets(tmp_path)
    assert any("High-entropy token" in f for f in findings)


def test_main_cli_success(tmp_path: Path) -> None:
    """Test CLI success execution pathway.

    Uses an empty repository with placeholder complete files.
    """
    # Create complete template files to satisfy doctor checks
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Project\n## Installation\n## Usage\n## Requirements\n## License\n"
    )
    gi = tmp_path / ".gitignore"
    gi.write_text(".venv/\n__pycache__/\nbuild/\n.vscode/\n.coverage\n")

    args = ["repo_doctor.py", str(tmp_path)]
    with patch("sys.argv", args):
        with pytest.raises(SystemExit) as exc:
            repo_doctor.main()
        assert exc.value.code == 0


def test_main_cli_failure(tmp_path: Path) -> None:
    """Test CLI failure execution pathway.

    Uses an empty folder to trigger missing README/gitignore errors.
    """
    args = ["repo_doctor.py", str(tmp_path)]
    with patch("sys.argv", args):
        with pytest.raises(SystemExit) as exc:
            repo_doctor.main()
        assert exc.value.code == 1
