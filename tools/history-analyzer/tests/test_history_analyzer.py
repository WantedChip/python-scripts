"""Tests for Command History Analyzer."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# pylint: disable=import-error, wrong-import-position
import history_analyzer  # noqa: E402


def test_get_default_history_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test standard file paths resolution based on shell inputs."""
    monkeypatch.setenv("HOME", "/dummy/home")
    monkeypatch.setenv("ZDOTDIR", "/dummy/zdot")
    monkeypatch.setenv("APPDATA", "/dummy/appdata")

    assert history_analyzer.get_default_history_path("bash") == Path(
        "/dummy/home/.bash_history"
    )
    assert history_analyzer.get_default_history_path("zsh") == Path(
        "/dummy/zdot/.zsh_history"
    )

    monkeypatch.delenv("ZDOTDIR", raising=False)
    assert history_analyzer.get_default_history_path("zsh") == Path(
        "/dummy/home/.zsh_history"
    )

    p = history_analyzer.get_default_history_path("powershell")
    assert p is not None

    with pytest.raises(ValueError):
        history_analyzer.get_default_history_path("unsupported_shell")


def test_parse_history_lines() -> None:
    """Test cleaning timestamps and other shell metadata logs."""
    zsh_raw = [
        ': 1690000000:0;git commit -m "fix"',
        ": 1690000001:0;docker compose up -d",
        "invalid_zsh_line",
    ]
    parsed_zsh = list(history_analyzer.parse_history_lines(zsh_raw, "zsh"))
    assert parsed_zsh == ['git commit -m "fix"', "docker compose up -d"]

    bash_raw = [
        "#1690000000",
        "git status",
        "ls -la",
    ]
    parsed_bash = list(history_analyzer.parse_history_lines(bash_raw, "bash"))
    assert parsed_bash == ["git status", "ls -la"]


def test_clean_base_command() -> None:
    """Test extracting base tool names and sub-commands."""
    assert history_analyzer.clean_base_command("git checkout main") == "git checkout"
    assert history_analyzer.clean_base_command("docker compose up") == "docker compose"
    assert history_analyzer.clean_base_command("python -m venv") == "python"
    assert history_analyzer.clean_base_command("ls -la") == "ls"
    assert history_analyzer.clean_base_command("") == ""


def test_suggest_alias() -> None:
    """Test alias generation maps and initials heuristics."""
    assert history_analyzer.suggest_alias("git checkout") == "gco"
    assert history_analyzer.suggest_alias("docker compose") == "dc"
    assert history_analyzer.suggest_alias("my long custom command") == "mlcc"
    assert history_analyzer.suggest_alias("short") == "sho"


def test_analyze_history(tmp_path: Path) -> None:
    """Test complete history parsing pipeline and suggests lists."""
    hist_file = tmp_path / "bash_hist.txt"
    lines = [
        'git commit -m "fix"',
        'git commit -m "fix"',
        'git commit -m "fix"',
        "docker compose down",
        "docker compose down",
        "ls -la",
    ]
    hist_file.write_text("\n".join(lines), encoding="utf-8")

    top_base, top_full, suggs = history_analyzer.analyze_history(
        hist_file, "bash", top_n=5
    )

    assert len(top_base) > 0
    assert top_base[0][0] == "git commit"
    assert top_base[0][1] == 3

    assert len(top_full) > 0
    assert top_full[0][0] == 'git commit -m "fix"'
    assert top_full[0][1] == 3

    # Suggestions check: git commit is multiword, count is 3
    assert len(suggs) > 0
    assert suggs[0][0] == 'git commit -m "fix"'


def test_main_cli_json_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI execution and JSON summaries export outputs."""
    hist_file = tmp_path / "bash_hist.txt"
    hist_file.write_text("git status\ngit status\n", encoding="utf-8")
    out_json = tmp_path / "out.json"

    args = [
        "history_analyzer.py",
        "-s",
        "bash",
        "-i",
        str(hist_file),
        "-o",
        str(out_json),
    ]
    monkeypatch.setattr(sys, "argv", args)
    history_analyzer.main()

    assert out_json.exists()
    saved = json.loads(out_json.read_text(encoding="utf-8"))
    assert saved["shell"] == "bash"
    assert saved["top_base_commands"][0]["command"] == "git status"


def test_get_default_history_path_posix(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test powershell path resolution fallback when APPDATA is unset."""
    monkeypatch.setenv("HOME", "/dummy/home")
    monkeypatch.delenv("APPDATA", raising=False)
    p = history_analyzer.get_default_history_path("powershell")
    assert p == Path("/dummy/home/.config/powershell/ConsoleHost_history.txt")


def test_parse_history_lines_malformed_zsh() -> None:
    """Test Zsh parser ignores lines starting with colon but without semicolon."""
    lines = [": 123456", ": 1690000002:0;git status"]
    res = list(history_analyzer.parse_history_lines(lines, "zsh"))
    assert res == ["git status"]


def test_main_cli_missing_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI exit code when target history file doesn't exist."""
    args = ["history_analyzer.py", "-s", "bash", "-i", "nonexistent_history_file"]
    monkeypatch.setattr(sys, "argv", args)
    with pytest.raises(SystemExit) as exc:
        history_analyzer.main()
    assert exc.value.code == 1


def test_main_cli_empty_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test CLI behavior with empty history logs."""
    hist = tmp_path / "empty_hist"
    hist.write_text("", encoding="utf-8")
    args = ["history_analyzer.py", "-s", "bash", "-i", str(hist)]
    monkeypatch.setattr(sys, "argv", args)
    with pytest.raises(SystemExit) as exc:
        history_analyzer.main()
    assert exc.value.code == 0


def test_print_terminal_summary() -> None:
    """Test console summaries output display formatting."""
    # Ensure no crashes on stdout writes
    history_analyzer.print_terminal_summary(
        "bash",
        [("git", 5)],
        [("git status", 3)],
        [("git checkout", 2, "gco")],
    )
