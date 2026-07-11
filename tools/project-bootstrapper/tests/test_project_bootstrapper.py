"""Tests for Project Bootstrapper."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# pylint: disable=import-error, wrong-import-position
import project_bootstrapper  # noqa: E402


def test_clean_project_name() -> None:
    """Test project and module name normalizations."""
    assert project_bootstrapper.clean_project_name("My Super App!") == (
        "MySuperApp",
        "mysuperapp",
    )
    assert project_bootstrapper.clean_project_name("123-app") == (
        "123-app",
        "_123_app",
    )


def test_write_file_no_overwrite(tmp_path: Path) -> None:
    """Test write_file respects existing file safety rules."""
    f = tmp_path / "exist.txt"
    f.write_text("orig", encoding="utf-8")

    # Should skip writing
    result = project_bootstrapper.write_file(f, "new", force=False)
    assert result is False
    assert f.read_text(encoding="utf-8") == "orig"

    # Should overwrite when force is true
    result2 = project_bootstrapper.write_file(f, "new", force=True)
    assert result2 is True
    assert f.read_text(encoding="utf-8") == "new"


def test_bootstrap_project_github_ci(tmp_path: Path) -> None:
    """Test standard template tree generation with Github CI enabled."""
    success = project_bootstrapper.bootstrap_project(
        tmp_path,
        "Antigravity Project",
        "A test template",
        ci_choice="github",
        force=False,
    )
    assert success is True

    root_dir = tmp_path / "AntigravityProject"
    assert root_dir.exists()
    assert (root_dir / "README.md").exists()
    assert (root_dir / ".gitignore").exists()
    assert (root_dir / "pyproject.toml").exists()
    assert (root_dir / "requirements-dev.txt").exists()
    assert (root_dir / "src" / "antigravityproject" / "__init__.py").exists()
    assert (root_dir / "src" / "antigravityproject" / "main.py").exists()
    assert (root_dir / "tests" / "test_main.py").exists()
    assert (root_dir / ".github" / "workflows" / "ci.yml").exists()

    readme_content = (root_dir / "README.md").read_text(encoding="utf-8")
    assert "AntigravityProject" in readme_content
    assert "A test template" in readme_content


def test_bootstrap_project_no_ci(tmp_path: Path) -> None:
    """Test scaffolding tree generation without Github Actions."""
    success = project_bootstrapper.bootstrap_project(
        tmp_path,
        "Antigravity Project",
        "A test template",
        ci_choice="none",
        force=False,
    )
    assert success is True

    root_dir = tmp_path / "AntigravityProject"
    assert not (root_dir / ".github" / "workflows" / "ci.yml").exists()


def test_main_cli_scaffold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI bootstrapping runs successfully."""
    args = [
        "project_bootstrapper.py",
        "-n",
        "CliApp",
        "-d",
        "CLI summary",
        "-o",
        str(tmp_path),
        "--ci",
        "none",
    ]
    monkeypatch.setattr(sys, "argv", args)
    project_bootstrapper.main()

    root_dir = tmp_path / "CliApp"
    assert root_dir.exists()
    assert (root_dir / "src" / "cliapp" / "main.py").exists()
