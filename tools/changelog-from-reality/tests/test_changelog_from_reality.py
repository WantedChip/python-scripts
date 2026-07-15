"""Tests for changelog-from-reality script."""

# pylint: disable=duplicate-code,wrong-import-position,line-too-long,import-error

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from changelog_from_reality import (  # noqa: E402
    GitCommandError,
    diff_python_structure,
    generate_markdown_changelog,
    get_changed_files,
    get_file_content,
    main,
    parse_structure,
    run_git,
)


@patch("subprocess.run")
def test_run_git_success(mock_run: MagicMock) -> None:
    """Test successful run_git command execution."""
    mock_run.return_value = MagicMock(returncode=0, stdout="diff output\n", stderr="")
    res = run_git(["diff"])
    assert res == "diff output"


@patch("subprocess.run")
def test_run_git_failure(mock_run: MagicMock) -> None:
    """Test run_git exception propagation."""
    import subprocess

    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=128, cmd=["git", "diff"], stderr="fatal: error"
    )
    with pytest.raises(GitCommandError) as excinfo:
        run_git(["diff"])
    assert "fatal: error" in str(excinfo.value)


@patch("changelog_from_reality.run_git")
def test_get_changed_files(mock_run_git: MagicMock) -> None:
    """Test fetching and parsing changed files list."""
    mock_run_git.return_value = (
        "A\tadded_file.py\nD\tdeleted_file.txt\nM\tmodified_file.py"
    )
    added, deleted, modified = get_changed_files(".", "HEAD~1", "HEAD")
    assert added == ["added_file.py"]
    assert deleted == ["deleted_file.txt"]
    assert modified == ["modified_file.py"]


@patch("changelog_from_reality.run_git")
def test_get_file_content(mock_run_git: MagicMock) -> None:
    """Test get_file_content retrieval."""
    mock_run_git.return_value = "content"
    assert get_file_content(".", "HEAD", "file.py") == "content"

    mock_run_git.side_effect = GitCommandError("error show")
    assert get_file_content(".", "HEAD", "file.py") is None


def test_parse_structure() -> None:
    """Test parse_structure on standard Python code."""
    source = (
        "def func(a: int) -> str:\n"
        "    '''Docstring'''\n"
        "    return str(a)\n\n"
        "class MyClass(Base):\n"
        "    def method(self):\n"
        "        pass\n"
    )
    funcs, classes = parse_structure(source)
    assert "func" in funcs
    assert funcs["func"].args_str == "a: int"
    assert funcs["func"].returns_str == "str"
    assert funcs["func"].docstring == "Docstring"

    assert "MyClass" in classes
    assert classes["MyClass"].bases == ["Base"]
    assert "method" in classes["MyClass"].methods

    # Test invalid syntax returns empty dictionaries
    bad_funcs, bad_classes = parse_structure("class MyClass invalid syntax:")
    assert bad_funcs == {}
    assert bad_classes == {}


def test_diff_python_structure() -> None:
    """Test diffing two Python sources with AST comparisons."""
    from_source = (
        "def old_func(x: int) -> None:\n"
        "    pass\n\n"
        "def sig_change(x: int) -> None:\n"
        "    pass\n\n"
        "def body_change() -> None:\n"
        "    print(1)\n\n"
        "class MyClass:\n"
        "    def m1(self):\n"
        "        pass\n"
    )

    to_source = (
        "def new_func() -> None:\n"
        "    pass\n\n"
        "def sig_change(x: int, y: str) -> str:\n"
        "    return y\n\n"
        "def body_change() -> None:\n"
        "    print(2)\n\n"
        "class MyClass(Base):\n"
        "    def m1(self):\n"
        "        print('updated')\n"
        "    def m2(self):\n"
        "        pass\n"
    )

    diffs = diff_python_structure(from_source, to_source)
    assert any("new_func" in f for f in diffs["added_funcs"])
    assert any("old_func" in f for f in diffs["removed_funcs"])
    assert any(
        "sig_change" in f and "signature changed" in f for f in diffs["modified_funcs"]
    )
    assert any(
        "body_change" in f and "logic updated" in f for f in diffs["modified_funcs"]
    )

    assert any("MyClass" in c for c in diffs["modified_classes"])
    assert any("base classes modified" in c for c in diffs["modified_classes"])
    assert any("added method" in c and "m2" in c for c in diffs["modified_classes"])
    assert any(
        "method" in c and "m1" in c and "updated" in c
        for c in diffs["modified_classes"]
    )


@patch("changelog_from_reality.get_file_content")
def test_generate_markdown_changelog(mock_get_content: MagicMock) -> None:
    """Test generate_markdown_changelog compiled output."""
    mock_get_content.side_effect = [
        "def func(): pass",  # from ref source
        "def func(a: int): pass",  # to ref source
    ]

    changelog = generate_markdown_changelog(
        from_ref="v1.0",
        to_ref="v2.0",
        added=["new_file.py"],
        deleted=["old_file.txt"],
        modified=["mod_file.py"],
        repo_path=".",
    )

    assert "# Changelog (from reality): v1.0 to v2.0" in changelog
    assert "## Added Files" in changelog
    assert "- `new_file.py`" in changelog
    assert "## Deleted Files" in changelog
    assert "- `old_file.txt`" in changelog
    assert "## Code Modifications" in changelog
    assert "mod_file.py" in changelog


@patch("changelog_from_reality.get_changed_files")
@patch("changelog_from_reality.generate_markdown_changelog")
@patch("builtins.print")
@patch("os.path.exists")
@patch("sys.argv")
def test_main_cli(
    mock_argv: MagicMock,
    mock_exists: MagicMock,
    mock_print: MagicMock,
    mock_generate: MagicMock,
    mock_get_files: MagicMock,
) -> None:
    """Test CLI parsing entry point."""
    mock_argv.__getitem__.side_effect = lambda x: [
        "changelog_from_reality.py",
        "v1.0",
        "v2.0",
    ][x]
    mock_argv.__len__.return_value = 3
    mock_exists.return_value = True

    mock_get_files.return_value = (["added.py"], [], [])
    mock_generate.return_value = "changelog content"

    main()
    mock_generate.assert_called_once()
    mock_print.assert_any_call("changelog content")
