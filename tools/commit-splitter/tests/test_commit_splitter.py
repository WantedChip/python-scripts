"""Unit tests for the commit-splitter CLI tool."""

# pylint: disable=duplicate-code,wrong-import-position,line-too-long,import-error

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from commit_splitter import (  # noqa: E402
    apply_commits,
    get_component_name,
    get_git_status,
    group_changes,
    main,
    print_suggestions,
    run_git,
    suggest_commit_message,
)


def test_run_git_success() -> None:
    """Tests successful git execution."""
    with patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "git output"
        mock_run.return_value = mock_res

        out = run_git(["status"])
        assert out == "git output"


def test_run_git_failure() -> None:
    """Tests git command failure handles stderr."""
    with patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_res.stderr = "git error"
        mock_run.return_value = mock_res

        with pytest.raises(RuntimeError, match="git error"):
            run_git(["status"])


def test_run_git_not_found() -> None:
    """Tests when git binary is not found on path."""
    with patch("subprocess.run", side_effect=FileNotFoundError("not found")):
        with pytest.raises(RuntimeError, match="Git command execution failed"):
            run_git(["status"])


def test_get_git_status_porcelain() -> None:
    """Tests get_git_status parses different porcelain status formats."""
    mock_out = (
        " M tools/fresh-machine/fresh_machine.py\n"
        "?? tools/fresh-machine/new_file.txt\n"
        "R  old_file.py -> new_file.py\n"
        ' A "tools/spaces in path.py"\n'
    )
    with patch("commit_splitter.run_git", return_value=mock_out):
        status = get_git_status()
        assert len(status) == 4
        assert status[0] == (" M", "tools/fresh-machine/fresh_machine.py")
        assert status[1] == ("??", "tools/fresh-machine/new_file.txt")
        assert status[2] == ("R ", "new_file.py")
        assert status[3] == (" A", "tools/spaces in path.py")


def test_get_git_status_error() -> None:
    """Tests get_git_status exits on Git runtime errors."""
    with patch(
        "commit_splitter.run_git", side_effect=RuntimeError("git error")
    ), pytest.raises(SystemExit):
        get_git_status()


def test_get_component_name() -> None:
    """Tests component extraction rules."""
    assert get_component_name("INDEX.md") == "global"
    assert get_component_name("tools/fresh-machine/fresh_machine.py") == "fresh-machine"
    assert get_component_name("checkers/api-monitor/api_monitor.py") == "api-monitor"
    assert get_component_name("src/utils.py") == "utils"
    assert get_component_name("tests/test_fresh_machine.py") == "fresh_machine"
    assert get_component_name("tests/test_utils.py") == "utils"
    assert get_component_name("misc/file.txt") == "misc"


def test_suggest_commit_message() -> None:
    """Tests commit message generation rules."""
    assert suggest_commit_message("global", ["pyproject.toml"]) == (
        "chore: update development dependencies and tools configuration"
    )
    assert suggest_commit_message("global", ["INDEX.md"]) == (
        "docs: update repository documentation indexes"
    )
    assert suggest_commit_message("global", ["other_infra.txt"]) == (
        "chore: update repository infrastructure files"
    )
    assert suggest_commit_message("fresh-machine", ["test_fresh_machine.py"]) == (
        "test(fresh-machine): add unit tests covering changes"
    )
    assert suggest_commit_message("fresh-machine", ["README.md"]) == (
        "docs(fresh-machine): update documentation notes"
    )
    assert suggest_commit_message("fresh-machine", ["fresh_machine.py"]) == (
        "feat(fresh-machine): implement core features and improvements"
    )
    assert suggest_commit_message("fresh-machine", ["assets/logo.png"]) == (
        "refactor(fresh-machine): update assets and resources"
    )


def test_group_changes() -> None:
    """Tests grouping rules and test pairing merges."""
    changes = [
        (" M", "tools/fresh-machine/fresh_machine.py"),
        ("??", "tools/fresh-machine/tests/test_fresh_machine.py"),
        (" A", "INDEX.md"),
    ]
    groups = group_changes(changes)
    assert "fresh-machine" in groups
    assert "global" in groups
    assert len(groups["fresh-machine"]) == 2
    assert "tools/fresh-machine/fresh_machine.py" in groups["fresh-machine"]
    assert "tools/fresh-machine/tests/test_fresh_machine.py" in groups["fresh-machine"]


def test_print_suggestions_empty() -> None:
    """Tests printed output when no changes are found."""
    with patch("builtins.print") as mock_print:
        print_suggestions({}, False)
        mock_print.assert_called_once_with("No changes detected in working tree.")


def test_print_suggestions_json() -> None:
    """Tests JSON formatted output."""
    groups = {
        "global": ["INDEX.md"],
        "fresh-machine": ["tools/fresh-machine/fresh_machine.py"],
    }
    with patch("builtins.print") as mock_print:
        print_suggestions(groups, True)
        mock_print.assert_called_once()
        # Verify JSON validity
        args, _ = mock_print.call_args
        data = json.loads(args[0])
        assert len(data) == 2
        assert data[0]["component"] == "fresh-machine"


def test_print_suggestions_text() -> None:
    """Tests standard human-readable text output."""
    groups = {
        "global": ["INDEX.md"],
        "fresh-machine": ["tools/fresh-machine/fresh_machine.py"],
    }
    with patch("builtins.print") as mock_print:
        print_suggestions(groups, False)
        assert mock_print.call_count > 3


def test_apply_commits_non_interactive() -> None:
    """Tests sequential non-interactive commit application."""
    groups = {
        "fresh-machine": ["tools/fresh-machine/fresh_machine.py"],
    }
    with patch("commit_splitter.run_git") as mock_run:
        apply_commits(groups, interactive=False)
        assert mock_run.call_count == 2
        # First call is add, second call is commit
        args_first = mock_run.call_args_list[0][0][0]
        args_second = mock_run.call_args_list[1][0][0]
        assert "add" in args_first
        assert "commit" in args_second


def test_apply_commits_interactive_yes() -> None:
    """Tests interactive commit confirmed with yes."""
    groups = {
        "fresh-machine": ["tools/fresh-machine/fresh_machine.py"],
    }
    with patch("commit_splitter.run_git") as mock_run, patch(
        "builtins.input", return_value="y"
    ):
        apply_commits(groups, interactive=True)
        assert mock_run.call_count == 2


def test_apply_commits_interactive_no() -> None:
    """Tests interactive commit skipped with no."""
    groups = {
        "fresh-machine": ["tools/fresh-machine/fresh_machine.py"],
    }
    with patch("commit_splitter.run_git") as mock_run, patch(
        "builtins.input", return_value="n"
    ):
        apply_commits(groups, interactive=True)
        mock_run.assert_not_called()


def test_apply_commits_interactive_quit() -> None:
    """Tests interactive loop terminates immediately on quit."""
    groups = {
        "fresh-machine": ["tools/fresh-machine/fresh_machine.py"],
        "git-time-machine": ["tools/git-time-machine/git_time_machine.py"],
    }
    with patch("commit_splitter.run_git") as mock_run, patch(
        "builtins.input", return_value="q"
    ):
        apply_commits(groups, interactive=True)
        mock_run.assert_not_called()


def test_apply_commits_interactive_edit() -> None:
    """Tests editing the proposed commit message."""
    groups = {
        "fresh-machine": ["tools/fresh-machine/fresh_machine.py"],
    }
    with patch("commit_splitter.run_git") as mock_run, patch(
        "builtins.input", side_effect=["e", "custom message"]
    ):
        apply_commits(groups, interactive=True)
        assert mock_run.call_count == 2
        args_second = mock_run.call_args_list[1][0][0]
        assert "custom message" in args_second


def test_apply_commits_failure_rollback() -> None:
    """Tests commit failure falls back to unstaging the group."""
    groups = {
        "fresh-machine": ["tools/fresh-machine/fresh_machine.py"],
    }

    # First git call (add) succeeds, second call (commit) raises error, reset succeeds
    def mock_run_git(args: list[str]) -> str:
        if "commit" in args:
            raise RuntimeError("commit failed")
        return ""

    with patch("commit_splitter.run_git", side_effect=mock_run_git) as mock_run:
        apply_commits(groups, interactive=False)
        # Should call add, commit, and reset
        assert mock_run.call_count == 3
        assert "reset" in mock_run.call_args_list[2][0][0]


def test_main_suggest() -> None:
    """Tests main function suggesting groups without committing."""
    test_args = ["commit_splitter.py"]
    with patch("sys.argv", test_args), patch(
        "commit_splitter.get_git_status", return_value=[]
    ), patch("commit_splitter.print_suggestions") as mock_suggest:
        main()
        mock_suggest.assert_called_once()


def test_main_apply() -> None:
    """Tests main function calling apply_commits with apply flag."""
    test_args = ["commit_splitter.py", "-a"]
    with patch("sys.argv", test_args), patch(
        "commit_splitter.get_git_status", return_value=[]
    ), patch("commit_splitter.apply_commits") as mock_apply:
        main()
        mock_apply.assert_called_once_with({}, False)
