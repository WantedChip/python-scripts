"""Unit tests for why_is_this_file_here.py."""

import os
import sys
from unittest.mock import mock_open, patch

import pytest

# Add script directory to path
sys.path.insert(0, "tools/why-is-this-file-here")

# pylint: disable=wrong-import-position
from why_is_this_file_here import (  # noqa: E402
    check_is_ignored,
    find_code_references,
    get_git_origin,
    get_last_modified,
    is_git_repo,
    main,
)


def test_is_git_repo_true():
    """Test is_git_repo returns True when git command succeeds."""
    mock_res = patch("subprocess.run").start()
    mock_res.return_value.returncode = 0
    try:
        assert is_git_repo("/dummy") is True
    finally:
        patch.stopall()


def test_is_git_repo_false():
    """Test is_git_repo returns False when git command fails."""
    mock_res = patch("subprocess.run").start()
    mock_res.return_value.returncode = 1
    try:
        assert is_git_repo("/dummy") is False
    finally:
        patch.stopall()


def test_is_git_repo_oserror():
    """Test is_git_repo returns False when git executable is not found."""
    with patch("subprocess.run", side_effect=OSError("not found")):
        assert is_git_repo("/dummy") is False


def test_get_git_origin_success():
    """Test get_git_origin parses commit logs correctly when file has history."""
    mock_res = patch("subprocess.run").start()
    mock_res.return_value.stdout = (
        "sha12345678|Author Name|3 days ago|introduced new feature\n"
    )
    try:
        sha, desc = get_git_origin("/dummy/repo/file.py", "/dummy/repo")
        assert sha == "sha12345"
        assert "Author Name" in desc
        assert "introduced new feature" in desc
    finally:
        patch.stopall()


def test_get_git_origin_short_format():
    """Test get_git_origin handles malformed/short log format gracefully."""
    mock_res = patch("subprocess.run").start()
    mock_res.return_value.stdout = "sha12345678|Author Name|3 days ago\n"
    try:
        sha, desc = get_git_origin("/dummy/repo/file.py", "/dummy/repo")
        assert sha == "Unknown"
        assert "No creation details logged" in desc
    finally:
        patch.stopall()


def test_get_git_origin_failure():
    """Test get_git_origin handles exceptions gracefully."""
    with patch("subprocess.run", side_effect=OSError("error")):
        sha, desc = get_git_origin("/dummy/repo/file.py", "/dummy/repo")
        assert sha == "Unknown"
        assert "No creation details logged" in desc


def test_get_last_modified_success():
    """Test get_last_modified parses latest commit info correctly."""
    mock_res = patch("subprocess.run").start()
    mock_res.return_value.stdout = (
        "sha99999999|Modifier Name|2 hours ago|updated something\n"
    )
    try:
        desc = get_last_modified("/dummy/repo/file.py", "/dummy/repo")
        assert "sha99999" in desc
        assert "Modifier Name" in desc
        assert "updated something" in desc
    finally:
        patch.stopall()


def test_get_last_modified_failure():
    """Test get_last_modified returns default message on subprocess exception."""
    with patch("subprocess.run", side_effect=OSError("error")):
        desc = get_last_modified("/dummy/repo/file.py", "/dummy/repo")
        assert desc == "Unknown last modify log."


def test_check_is_ignored_true():
    """Test check_is_ignored returns True when file is ignored by git."""
    mock_res = patch("subprocess.run").start()
    mock_res.return_value.returncode = 0
    try:
        assert check_is_ignored("/dummy/repo/ignored.log", "/dummy/repo") is True
    finally:
        patch.stopall()


def test_check_is_ignored_false():
    """Test check_is_ignored returns False when file is not ignored."""
    mock_res = patch("subprocess.run").start()
    mock_res.return_value.returncode = 1
    try:
        assert check_is_ignored("/dummy/repo/not_ignored.py", "/dummy/repo") is False
    finally:
        patch.stopall()


def test_check_is_ignored_exception():
    """Test check_is_ignored returns False on exception."""
    with patch("subprocess.run", side_effect=OSError("git error")):
        assert check_is_ignored("/dummy/repo/ignored.log", "/dummy/repo") is False


def test_find_code_references():
    """Test find_code_references walks project files, skipping excludes."""
    repo_path = "/dummy/repo"
    file_path = "/dummy/repo/foo.py"

    walk_data = [
        ("/dummy/repo", ["venv", "src"], ["main.py", "logo.png", "foo.py"]),
        ("/dummy/repo/src", [], ["helper.py", "bad_file.bin"]),
    ]

    def mock_open_impl(filename, *args, **kwargs):
        content = ""
        if "main.py" in filename:
            content = "import foo\nprint('hello')\n"
        elif "helper.py" in filename:
            content = "from . import foo\n"
        return mock_open(read_data=content).return_value

    with patch("os.walk", return_value=walk_data), patch(
        "builtins.open", side_effect=mock_open_impl
    ):
        refs = find_code_references(file_path, repo_path)
        assert len(refs) == 2
        ref_files = [r[0] for r in refs]
        assert "main.py" in ref_files or os.path.join("src", "helper.py") in ref_files


def test_find_code_references_oserror():
    """Test find_code_references handles OS read errors gracefully."""
    walk_data = [
        ("/dummy/repo", [], ["main.py"]),
    ]
    with patch("os.walk", return_value=walk_data), patch(
        "builtins.open", side_effect=OSError("permission denied")
    ):
        refs = find_code_references("/dummy/repo/foo.py", "/dummy/repo")
        assert len(refs) == 0


@patch("os.path.exists", return_value=False)
def test_main_file_not_exists(mock_exists):
    """Test main exits with 1 if target file does not exist."""
    with patch("sys.argv", ["why_is_this_file_here", "missing.py"]), pytest.raises(
        SystemExit
    ) as excinfo:
        main()
    assert excinfo.value.code == 1


@patch("os.path.exists", return_value=True)
@patch("os.getcwd", return_value="/dummy/repo")
@patch("why_is_this_file_here.is_git_repo", return_value=True)
@patch(
    "why_is_this_file_here.get_git_origin", return_value=("sha123", "created by user")
)
@patch("why_is_this_file_here.get_last_modified", return_value="sha456 updated it")
@patch("why_is_this_file_here.check_is_ignored", return_value=True)
@patch("why_is_this_file_here.find_code_references", return_value=[])
@patch("builtins.print")
def test_main_safety_rating_high(
    mock_print,
    mock_refs,
    mock_ignored,
    mock_last_mod,
    mock_origin,
    mock_in_git,
    mock_cwd,
    mock_exists,
):
    """Test main prints HIGH safety rating for ignored file with no references."""
    with patch("sys.argv", ["why_is_this_file_here", "dummy.py"]), patch(
        "builtins.open", mock_open(read_data="some manual code")
    ):
        main()

    printed_lines = [call.args[0] for call in mock_print.call_args_list if call.args]
    assert any("[Safety Rating: HIGH]" in line for line in printed_lines)


@patch("os.path.exists", return_value=True)
@patch("os.getcwd", return_value="/dummy/repo")
@patch("why_is_this_file_here.is_git_repo", return_value=True)
@patch(
    "why_is_this_file_here.get_git_origin", return_value=("sha123", "created by user")
)
@patch("why_is_this_file_here.get_last_modified", return_value="sha456 updated it")
@patch("why_is_this_file_here.check_is_ignored", return_value=False)
@patch("why_is_this_file_here.find_code_references", return_value=[])
@patch("builtins.print")
def test_main_safety_rating_medium(
    mock_print,
    mock_refs,
    mock_ignored,
    mock_last_mod,
    mock_origin,
    mock_in_git,
    mock_cwd,
    mock_exists,
):
    """Test main prints MEDIUM safety rating for non-ignored manual file."""
    with patch("sys.argv", ["why_is_this_file_here", "dummy.py"]), patch(
        "builtins.open", mock_open(read_data="manual code")
    ):
        main()

    printed_lines = [call.args[0] for call in mock_print.call_args_list if call.args]
    assert any("[Safety Rating: MEDIUM]" in line for line in printed_lines)


@patch("os.path.exists", return_value=True)
@patch("os.getcwd", return_value="/dummy/repo")
@patch("why_is_this_file_here.is_git_repo", return_value=True)
@patch(
    "why_is_this_file_here.get_git_origin", return_value=("sha123", "created by user")
)
@patch("why_is_this_file_here.get_last_modified", return_value="sha456 updated it")
@patch("why_is_this_file_here.check_is_ignored", return_value=False)
@patch("why_is_this_file_here.find_code_references", return_value=[("another.py", 10)])
@patch("builtins.print")
def test_main_safety_rating_low(
    mock_print,
    mock_refs,
    mock_ignored,
    mock_last_mod,
    mock_origin,
    mock_in_git,
    mock_cwd,
    mock_exists,
):
    """Test main prints LOW safety rating when active codebase references exist."""
    with patch("sys.argv", ["why_is_this_file_here", "dummy.py"]), patch(
        "builtins.open", mock_open(read_data="manual code")
    ):
        main()

    printed_lines = [call.args[0] for call in mock_print.call_args_list if call.args]
    assert any("[Safety Rating: LOW]" in line for line in printed_lines)


@patch("os.path.exists", return_value=True)
@patch("os.getcwd", return_value="/dummy/repo")
@patch("why_is_this_file_here.is_git_repo", return_value=False)
@patch("builtins.print")
def test_main_not_in_git(mock_print, mock_in_git, mock_cwd, mock_exists):
    """Test main diagnostics output when not inside a git repository."""
    with patch("sys.argv", ["why_is_this_file_here", "dummy.py"]), patch(
        "builtins.open", mock_open(read_data="manual code")
    ):
        main()

    printed_lines = [call.args[0] for call in mock_print.call_args_list if call.args]
    assert any(
        "Target path not inside a Git repository" in line for line in printed_lines
    )


@patch("os.path.exists", return_value=True)
@patch("os.getcwd", return_value="/dummy/repo")
@patch("why_is_this_file_here.is_git_repo", return_value=True)
@patch(
    "why_is_this_file_here.get_git_origin", return_value=("sha123", "created by user")
)
@patch("why_is_this_file_here.get_last_modified", return_value="sha456 updated it")
@patch("why_is_this_file_here.check_is_ignored", return_value=False)
@patch("why_is_this_file_here.find_code_references", return_value=[])
@patch("builtins.print")
def test_main_auto_generated_header(
    mock_print,
    mock_refs,
    mock_ignored,
    mock_last_mod,
    mock_origin,
    mock_in_git,
    mock_cwd,
    mock_exists,
):
    """Test main detects auto-generated files by scanning top lines."""
    with patch("sys.argv", ["why_is_this_file_here", "dummy.py"]), patch(
        "builtins.open",
        mock_open(
            read_data="// This file is auto-generated by the compiler. Do not edit!"
        ),
    ):
        main()

    printed_lines = [call.args[0] for call in mock_print.call_args_list if call.args]
    assert any("auto-generator warnings" in line for line in printed_lines)
    assert any("[Safety Rating: HIGH]" in line for line in printed_lines)


@patch("os.path.exists", return_value=True)
@patch("os.getcwd", return_value="/dummy/repo")
@patch("why_is_this_file_here.is_git_repo", return_value=True)
@patch(
    "why_is_this_file_here.get_git_origin", return_value=("sha123", "created by user")
)
@patch("why_is_this_file_here.get_last_modified", return_value="sha456 updated it")
@patch("why_is_this_file_here.check_is_ignored", return_value=False)
@patch("why_is_this_file_here.find_code_references", return_value=[])
@patch("builtins.print")
def test_main_in_build_folder(
    mock_print,
    mock_refs,
    mock_ignored,
    mock_last_mod,
    mock_origin,
    mock_in_git,
    mock_cwd,
    mock_exists,
):
    """Test main flags files located in standard build/dist paths."""
    with patch(
        "sys.argv", ["why_is_this_file_here", "/dummy/repo/build/output.o"]
    ), patch("builtins.open", mock_open(read_data="binary_data")):
        main()

    printed_lines = [call.args[0] for call in mock_print.call_args_list if call.args]
    assert any("build/distribution folders" in line for line in printed_lines)
    assert any("[Safety Rating: HIGH]" in line for line in printed_lines)


@patch("os.path.exists", return_value=True)
@patch("os.getcwd", return_value="/dummy/repo")
@patch("why_is_this_file_here.is_git_repo", return_value=True)
@patch(
    "why_is_this_file_here.get_git_origin", return_value=("sha123", "created by user")
)
@patch("why_is_this_file_here.get_last_modified", return_value="sha456 updated it")
@patch("why_is_this_file_here.check_is_ignored", return_value=False)
@patch("why_is_this_file_here.find_code_references", return_value=[])
@patch("builtins.print")
def test_main_file_read_error(
    mock_print,
    mock_refs,
    mock_ignored,
    mock_last_mod,
    mock_origin,
    mock_in_git,
    mock_cwd,
    mock_exists,
):
    """Test main handles file opening errors gracefully when scanning headers."""
    with patch("sys.argv", ["why_is_this_file_here", "dummy.py"]), patch(
        "builtins.open", side_effect=OSError("access denied")
    ):
        main()

    printed_lines = [call.args[0] for call in mock_print.call_args_list if call.args]
    assert any("manually written codebase asset" in line for line in printed_lines)
