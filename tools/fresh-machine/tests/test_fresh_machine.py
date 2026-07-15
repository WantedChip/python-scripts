"""Unit tests for Fresh Machine setup replication utility."""

# pylint: disable=duplicate-code,wrong-import-position

import json
import os
import subprocess
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# Add current folder to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# pylint: disable=import-error
from fresh_machine import (  # noqa: E402
    export_setup,
    get_git_config,
    get_python_tools,
    get_shell_aliases,
    get_system_packages,
    get_vscode_extensions,
    restore_setup,
    run_command,
)


def test_run_command_success() -> None:
    """Tests run_command returns output on success."""
    with patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "output-content\n"
        mock_run.return_value = mock_res

        out = run_command(["some", "cmd"])
        assert out == "output-content\n"
        mock_run.assert_called_once_with(
            ["some", "cmd"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )


def test_run_command_failure() -> None:
    """Tests run_command returns empty string on failure or exception."""
    with patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_run.return_value = mock_res

        assert run_command(["fail"]) == ""

        # Test OSError/FileNotFoundError
        mock_run.side_effect = FileNotFoundError()
        assert run_command(["missing"]) == ""


def test_get_git_config() -> None:
    """Tests parsing of Git global configurations."""
    mock_out = "user.name=Test User\nuser.email=test@example.com\ncore.editor=nano\n"
    with patch("fresh_machine.run_command", return_value=mock_out):
        cfg = get_git_config()
        assert cfg == {
            "user.name": "Test User",
            "user.email": "test@example.com",
            "core.editor": "nano",
        }


def test_get_vscode_extensions() -> None:
    """Tests listing VS Code extensions."""
    mock_out = "ms-python.python\nms-vscode.cpptools\n"
    with patch("fresh_machine.run_command", return_value=mock_out):
        exts = get_vscode_extensions()
        assert exts == ["ms-python.python", "ms-vscode.cpptools"]


def test_get_shell_aliases() -> None:
    """Tests parsing shell profile files for custom alias declarations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mock_home = tmpdir
        # Create mock shell profiles
        bashrc_path = os.path.join(mock_home, ".bashrc")
        zshrc_path = os.path.join(mock_home, ".zshrc")

        with open(bashrc_path, "w", encoding="utf-8") as f:
            f.write("alias ll='ls -la'\n")
            f.write("alias gs='git status'\n")
            f.write("export PATH=$PATH:/some/bin\n")

        with open(zshrc_path, "w", encoding="utf-8") as f:
            f.write("alias gd='git diff'\n")
            f.write("alias gs='git status'\n")  # duplicate

        with patch("os.path.expanduser", return_value=mock_home):
            aliases = get_shell_aliases()
            assert "alias ll='ls -la'" in aliases
            assert "alias gs='git status'" in aliases
            assert "alias gd='git diff'" in aliases
            assert len(aliases) == 3


def test_get_system_packages_windows() -> None:
    """Tests package list retrieval on Windows platforms."""
    winget_out = (
        "Name    Id    Version\n"
        "---------------------\n"
        "Git     Git.Git    2.40.0\n"
        "Python  Python.Python.3.11  3.11.0\n"
    )
    choco_out = "git 2.40.0\npython3 3.11.0\n"

    with patch("platform.system", return_value="Windows"):

        def mock_run(run_args: list[str]) -> str:
            if "winget" in run_args:
                return winget_out
            if "choco" in run_args:
                return choco_out
            return ""

        with patch("fresh_machine.run_command", side_effect=mock_run):
            pkgs = get_system_packages()
            assert "winget" in pkgs
            assert "choco" in pkgs
            assert pkgs["winget"] == ["Git.Git", "Python.Python.3.11"]
            assert pkgs["choco"] == ["git", "python3"]


def test_get_system_packages_macos() -> None:
    """Tests package list retrieval on macOS platforms."""
    brew_leaves_out = "jq\nripgrep\n"
    brew_casks_out = "docker\nvisual-studio-code\n"

    with patch("platform.system", return_value="Darwin"):

        def mock_run(run_args: list[str]) -> str:
            if "leaves" in run_args:
                return brew_leaves_out
            if "--cask" in run_args:
                return brew_casks_out
            return ""

        with patch("fresh_machine.run_command", side_effect=mock_run):
            pkgs = get_system_packages()
            assert pkgs["brew_formulae"] == ["jq", "ripgrep"]
            assert pkgs["brew_casks"] == ["docker", "visual-studio-code"]


def test_get_system_packages_linux() -> None:
    """Tests package list retrieval on Linux platforms."""
    apt_out = "curl\ntcpdump\n"
    pacman_out = "git 2.40.0-1\nvim 9.0.0-1\n"

    with patch("platform.system", return_value="Linux"):

        def mock_run(run_args: list[str]) -> str:
            if "apt-mark" in run_args:
                return apt_out
            if "pacman" in run_args:
                return pacman_out
            return ""

        with patch("fresh_machine.run_command", side_effect=mock_run):
            pkgs = get_system_packages()
            assert pkgs["apt"] == ["curl", "tcpdump"]
            assert pkgs["pacman"] == ["git", "vim"]


def test_get_python_tools_pipx() -> None:
    """Tests python package retrieval preferring pipx."""
    pipx_out = "black 23.3.0\nflake8 6.0.0\n"
    with patch("fresh_machine.run_command", return_value=pipx_out):
        tools = get_python_tools()
        assert tools == ["black", "flake8"]


def test_get_python_tools_pip() -> None:
    """Tests python package retrieval fallback to pip list JSON."""
    pip_json = json.dumps([{"name": "requests", "version": "2.31.0"}])

    def mock_run(run_args: list[str]) -> str:
        if "pipx" in run_args:
            return ""
        if "pip" in run_args:
            return pip_json
        return ""

    with patch("fresh_machine.run_command", side_effect=mock_run):
        tools = get_python_tools()
        assert tools == ["requests"]


def test_export_setup() -> None:
    """Tests gathering profile values and exporting setup JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_file = os.path.join(tmpdir, "profile.json")

        p1 = patch("fresh_machine.get_git_config", return_value={"user.name": "Alice"})
        p2 = patch("fresh_machine.get_vscode_extensions", return_value=["ms-python"])
        p3 = patch("fresh_machine.get_shell_aliases", return_value=["alias ll"])
        p4 = patch("fresh_machine.get_system_packages", return_value={"winget": ["G"]})
        p5 = patch("fresh_machine.get_python_tools", return_value=["pipx"])

        with p1, p2, p3, p4, p5:

            export_setup(out_file)

            assert os.path.exists(out_file)
            with open(out_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert data["git_config"] == {"user.name": "Alice"}
            assert data["vscode_extensions"] == ["ms-python"]
            assert data["shell_aliases"] == ["alias ll"]
            assert data["system_packages"] == {"winget": ["G"]}
            assert data["python_tools"] == ["pipx"]


def test_export_setup_error() -> None:
    """Tests export setup handles write failure gracefully."""
    with pytest.raises(SystemExit):
        export_setup("/nonexistent_dir/profile.json")


def test_restore_setup_dry_run() -> None:
    """Tests restore_setup performs correct command translations in dry-run mode."""
    profile_data = {
        "git_config": {"user.name": "Bob"},
        "shell_aliases": ["alias gs='git status'"],
        "vscode_extensions": ["ms-python.python"],
        "system_packages": {
            "winget": ["Git.Git"],
            "choco": ["curl"],
            "brew_formulae": ["jq"],
            "brew_casks": ["docker"],
            "apt": ["vim"],
            "pacman": ["neovim"],
        },
        "python_tools": ["black"],
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        prof_file = os.path.join(tmpdir, "restore_profile.json")
        with open(prof_file, "w", encoding="utf-8") as f:
            json.dump(profile_data, f)

        with patch("subprocess.run") as mock_run, patch(
            "fresh_machine.run_command", return_value="1.0.0"
        ):

            restore_setup(prof_file, dry_run=True)
            # In dry-run, subprocess.run should never be called.
            mock_run.assert_not_called()


def test_restore_setup_active() -> None:
    """Tests restore_setup runs active restoration commands."""
    profile_data = {
        "git_config": {"user.name": "Bob"},
        "shell_aliases": ["alias gs='git status'"],
        "vscode_extensions": ["ms-python.python"],
        "system_packages": {
            "winget": ["Git.Git"],
        },
        "python_tools": ["black"],
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        prof_file = os.path.join(tmpdir, "restore_profile.json")
        with open(prof_file, "w", encoding="utf-8") as f:
            json.dump(profile_data, f)

        mock_home = tmpdir
        zshrc_path = os.path.join(mock_home, ".zshrc")
        # Pre-seed zshrc
        with open(zshrc_path, "w", encoding="utf-8") as f:
            f.write("# Existing file\n")

        with patch("subprocess.run") as mock_run, patch(
            "os.path.expanduser", return_value=mock_home
        ), patch("os.environ", {"SHELL": "/bin/zsh"}), patch(
            "fresh_machine.run_command", return_value="1.0.0"
        ):

            restore_setup(prof_file, dry_run=False)
            assert mock_run.call_count >= 4  # git config, vscode, winget, python tool

            # Check alias was appended
            with open(zshrc_path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "alias gs='git status'" in content


def test_restore_setup_invalid_profile() -> None:
    """Tests restore_setup fails on invalid profile JSON."""
    with pytest.raises(SystemExit):
        restore_setup("nonexistent_profile.json", dry_run=False)
