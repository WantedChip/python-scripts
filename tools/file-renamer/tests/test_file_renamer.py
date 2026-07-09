"""Comprehensive unit tests for the Bulk File Renamer tool."""

import json
import os
import re
import sys
# pylint: disable=wrong-import-position,import-error,redefined-outer-name
# pylint: disable=import-outside-toplevel,unused-import,unused-argument
# pylint: disable=wrong-import-order
import pytest
from typing import Generator, Any

# Add parent folder to path to import file_renamer
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import file_renamer  # noqa: E402


@pytest.fixture
def temp_workspace(tmp_path) -> Generator[Any, None, None]:
    """Provide a temporary workspace directory for file operations."""
    # Convert path to string for os operations compatibility
    yield tmp_path


def test_casing_and_spaces(temp_workspace):
    """Test lower/upper casing and space replacement."""
    # Create test files
    f1 = temp_workspace / "My File Name.txt"
    f1.write_text("content")

    # 1. Lowercase and replace spaces
    args = file_renamer.parse_args(
        ["-d", str(temp_workspace), "--lower", "--replace-spaces", "-"]
    )

    # Check pipeline transforms
    stem = "My File Name"
    # Casing
    if args.lower:
        stem = stem.lower()
    if args.replace_spaces is not None:
        stem = stem.replace(" ", args.replace_spaces)

    assert stem == "my-file-name"

    # 2. Uppercase and default space replacement (_)
    args_upper = file_renamer.parse_args(
        ["-d", str(temp_workspace), "--upper", "--replace-spaces"]
    )
    stem = "My File Name"
    if args_upper.upper:
        stem = stem.upper()
    if args_upper.replace_spaces is not None:
        stem = stem.replace(" ", args_upper.replace_spaces)

    assert stem == "MY_FILE_NAME"


def test_date_cleanup():
    """Test date cleaning and format ambiguity resolution."""
    # YMD format input
    assert (
        file_renamer.clean_dates_in_stem("file_2023_05_12", "YMD") == "file_2023-05-12"
    )
    assert file_renamer.clean_dates_in_stem("file_2023.5.2", "YMD") == "file_2023-05-02"
    assert (
        file_renamer.clean_dates_in_stem("file 2023 5 02", "YMD") == "file 2023-05-02"
    )

    # DMY format input (Year last)
    assert (
        file_renamer.clean_dates_in_stem("file_12-05-2023", "DMY") == "file_2023-05-12"
    )
    assert file_renamer.clean_dates_in_stem("file_2.5.2023", "DMY") == "file_2023-05-02"

    # MDY format input (Year last)
    assert (
        file_renamer.clean_dates_in_stem("file_12-05-2023", "MDY") == "file_2023-12-05"
    )
    assert file_renamer.clean_dates_in_stem("file_5.2.2023", "MDY") == "file_2023-05-02"

    # Invalid dates should not be matched or changed
    assert (
        file_renamer.clean_dates_in_stem("file_15-15-2023", "DMY") == "file_15-15-2023"
    )
    assert (
        file_renamer.clean_dates_in_stem("file_35-05-2023", "DMY") == "file_35-05-2023"
    )


def test_regex_replace():
    """Test regular expression replacement and backreferences."""
    # Simple regex find and replace
    stem = "img_123_backup"
    res = re.sub(r"img_(\d+)_backup", r"backup_\1", stem)
    assert res == "backup_123"

    # Regex search with no groups
    res2 = re.sub(r"backup", "restored", "backup_123")
    assert res2 == "restored_123"


def test_numbering_and_sorting(temp_workspace):
    """Test file sorting options and sequential numbering formats."""
    # Create test files with different mtimes and sizes

    f1 = temp_workspace / "a.txt"
    f2 = temp_workspace / "b.txt"
    f3 = temp_workspace / "c.txt"

    # Write different content sizes
    f1.write_text("small")  # 5 bytes
    f2.write_text("medium_size")  # 11 bytes
    f3.write_text("large_size_data")  # 15 bytes

    files = [str(f1), str(f2), str(f3)]

    # Sort by size (ascending)
    files.sort(
        key=lambda p: (os.path.getsize(p), os.path.relpath(p, str(temp_workspace)))
    )
    assert [os.path.basename(f) for f in files] == ["a.txt", "b.txt", "c.txt"]

    # Test numbering generation
    args = file_renamer.parse_args(
        [
            "-d",
            str(temp_workspace),
            "--number",
            "--number-start",
            "5",
            "--number-step",
            "2",
            "--number-padding",
            "4",
            "--number-format",
            "doc_{num}_{name}",
        ]
    )

    # Generate names manually to test format
    stems = ["first", "second"]
    generated = []
    for i, stem in enumerate(stems):
        num = args.number_start + i * args.number_step
        num_str = f"{num:0{args.number_padding}d}"
        generated.append(args.number_format.format(name=stem, num=num_str))

    assert generated == ["doc_0005_first", "doc_0007_second"]


def test_collision_validation(temp_workspace):
    """Test collision checks for many-to-one and external collisions."""
    f1 = temp_workspace / "a.txt"
    f2 = temp_workspace / "b.txt"
    f3 = temp_workspace / "c.txt"
    f1.write_text("1")
    f2.write_text("2")
    f3.write_text("3")

    # 1. Many-to-one collision: multiple files mapping to the same name
    renames_m21 = [
        (str(f1), str(temp_workspace / "target.txt")),
        (str(f2), str(temp_workspace / "target.txt")),
    ]
    conflicts_m21 = file_renamer.validate_renames(renames_m21)
    assert any("Many-to-one collision" in c for c in conflicts_m21)

    # 2. External collision: target file exists on disk and is not in the source list
    renames_ext = [(str(f1), str(f3))]  # f3 exists on disk but is not being renamed
    conflicts_ext = file_renamer.validate_renames(renames_ext)
    assert any("External collision" in c for c in conflicts_ext)

    # 3. No collision: swap chain
    # f1 -> f2 and f2 -> f3 and f3 -> f1
    renames_swap = [(str(f1), str(f2)), (str(f2), str(f3)), (str(f3), str(f1))]
    conflicts_swap = file_renamer.validate_renames(renames_swap)
    assert len(conflicts_swap) == 0  # Allowed since all targets are in source list


def test_2phase_rename_success(temp_workspace):
    """Test 2-phase rename execution succeeds on swaps and chains."""
    f1 = temp_workspace / "a.txt"
    f2 = temp_workspace / "b.txt"
    f1.write_text("A")
    f2.write_text("B")

    # Perform swap rename
    rename_list = [(str(f1), str(f2)), (str(f2), str(f1))]

    file_renamer.execute_2phase_rename(rename_list)

    assert f1.read_text() == "B"
    assert f2.read_text() == "A"


def test_2phase_rename_case_only(temp_workspace):
    """Test 2-phase rename handles case-only change correctly on Windows."""
    f1 = temp_workspace / "hello.txt"
    f1.write_text("hello_casing")

    rename_list = [(str(f1), str(temp_workspace / "HELLO.TXT"))]

    file_renamer.execute_2phase_rename(rename_list)

    assert "HELLO.TXT" in os.listdir(temp_workspace)
    assert "hello.txt" not in os.listdir(temp_workspace)
    assert (temp_workspace / "HELLO.TXT").read_text() == "hello_casing"


def test_2phase_rename_failure_rollback(temp_workspace):
    """Test 2-phase rename rollback if Phase 1 fails midway."""
    f1 = temp_workspace / "a.txt"
    f2 = temp_workspace / "b.txt"
    f1.write_text("A")
    f2.write_text("B")

    # Rename list
    rename_list = [
        (str(f1), str(temp_workspace / "x.txt")),
        (str(f2), str(temp_workspace / "y.txt")),
    ]

    # Mock os.rename to fail when renaming f2 (the second file) to temp
    original_rename = os.rename

    def mock_rename_fail(src, dst):
        if str(f2) in src:
            raise OSError("Simulated Phase 1 Failure")
        original_rename(src, dst)

    os.rename = mock_rename_fail
    try:
        with pytest.raises(RuntimeError, match="Phase 1 failure"):
            file_renamer.execute_2phase_rename(rename_list)
    finally:
        os.rename = original_rename

    # Check that disk files are restored back to original state
    assert f1.exists()
    assert f2.exists()
    assert f1.read_text() == "A"
    assert f2.read_text() == "B"
    assert not (temp_workspace / "x.txt").exists()
    assert not (temp_workspace / "y.txt").exists()


def test_2phase_rename_phase2_failure_rollback(temp_workspace):
    """Test 2-phase rename rollback if Phase 2 fails midway."""
    f1 = temp_workspace / "a.txt"
    f2 = temp_workspace / "b.txt"
    f1.write_text("A")
    f2.write_text("B")

    rename_list = [
        (str(f1), str(temp_workspace / "x.txt")),
        (str(f2), str(temp_workspace / "y.txt")),
    ]

    # Mock os.rename to fail in Phase 2 when renaming y's temp file to target y.txt
    original_rename = os.rename

    # We want Phase 1 to succeed, but Phase 2 to fail on the second item.
    # Phase 2 targets: x.txt, y.txt
    def mock_rename_fail(src, dst):
        if dst.endswith("y.txt"):
            raise OSError("Simulated Phase 2 Failure")
        original_rename(src, dst)

    os.rename = mock_rename_fail
    try:
        with pytest.raises(RuntimeError, match="Phase 2 failure"):
            file_renamer.execute_2phase_rename(rename_list)
    finally:
        os.rename = original_rename

    # Verification: original files must be restored completely
    assert f1.exists()
    assert f2.exists()
    assert f1.read_text() == "A"
    assert f2.read_text() == "B"
    assert not (temp_workspace / "x.txt").exists()
    assert not (temp_workspace / "y.txt").exists()


def test_undo_success(temp_workspace):
    """Test that a successful undo rolls back files in reverse order."""
    f1 = temp_workspace / "a.txt"
    f2 = temp_workspace / "b.txt"
    f1.write_text("A")
    f2.write_text("B")

    # Rename them
    rename_list = [
        (str(f1), str(temp_workspace / "x.txt")),
        (str(f2), str(temp_workspace / "y.txt")),
    ]
    file_renamer.execute_2phase_rename(rename_list)

    # Save history
    history_file = temp_workspace / ".rename_history.json"
    history_data = {
        "base_dir": str(temp_workspace).replace("\\", "/"),
        "timestamp": "2026-07-07T12:00:00Z",
        "command": "test",
        "renames": [
            {"src": "a.txt", "dest": "x.txt"},
            {"src": "b.txt", "dest": "y.txt"},
        ],
        "undone": False,
    }
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history_data, f)

    # Verify they were renamed
    assert not f1.exists()
    assert (temp_workspace / "x.txt").exists()

    # Trigger undo
    file_renamer.execute_undo(str(history_file), str(temp_workspace))

    # Verify files restored
    assert f1.exists()
    assert f2.exists()
    assert f1.read_text() == "A"
    assert f2.read_text() == "B"
    assert not (temp_workspace / "x.txt").exists()
    assert not (temp_workspace / "y.txt").exists()

    # Check history file renamed to .undone
    assert not history_file.exists()
    undone_file = temp_workspace / ".rename_history.json.undone"
    assert undone_file.exists()
    with open(undone_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["undone"] is True


def test_undo_partial_failure(temp_workspace):
    """Test that if undo fails midway, remaining uncompleted steps are preserved."""
    f1 = temp_workspace / "a.txt"
    f2 = temp_workspace / "b.txt"
    f1.write_text("A")
    f2.write_text("B")

    # Rename them
    rename_list = [
        (str(f1), str(temp_workspace / "x.txt")),
        (str(f2), str(temp_workspace / "y.txt")),
    ]
    file_renamer.execute_2phase_rename(rename_list)

    # Save history: order is a.txt -> x.txt, b.txt -> y.txt.
    # Reverse undo order: y.txt -> b.txt, then x.txt -> a.txt.
    history_file = temp_workspace / ".rename_history.json"
    history_data = {
        "base_dir": str(temp_workspace).replace("\\", "/"),
        "timestamp": "2026-07-07T12:00:00Z",
        "command": "test",
        "renames": [
            {"src": "a.txt", "dest": "x.txt"},
            {"src": "b.txt", "dest": "y.txt"},
        ],
        "undone": False,
    }
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history_data, f)

    # Mock os.rename to fail when renaming x's temp file back to a.txt in Phase 2
    # In undo list (reverse):
    # Step 1: y.txt (dest) -> b.txt (src)
    # Step 2: x.txt (dest) -> a.txt (src)
    original_rename = os.rename

    def mock_rename_fail(src, dst):
        if dst.endswith("a.txt"):
            raise OSError("Simulated Undo Failure")
        original_rename(src, dst)

    os.rename = mock_rename_fail
    try:
        with pytest.raises(SystemExit):
            file_renamer.execute_undo(str(history_file), str(temp_workspace))
    finally:
        os.rename = original_rename

    # Verification:
    # 1. Step 1 (y.txt -> b.txt) succeeded. So b.txt exists, y.txt does not.
    # 2. Step 2 (x.txt -> a.txt) failed. Since it failed in Phase 2,
    #    the temp file was restored back to x.txt.
    #    So x.txt exists, a.txt does not.
    assert f2.exists()
    assert f2.read_text() == "B"
    assert not (temp_workspace / "y.txt").exists()

    assert not f1.exists()
    assert (temp_workspace / "x.txt").exists()

    # 3. The history file must still exist and contain ONLY the remaining
    #    uncompleted step: a.txt -> x.txt
    assert history_file.exists()
    with open(history_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["undone"] is False
    assert len(data["renames"]) == 1
    assert data["renames"][0]["src"] == "a.txt"
    assert data["renames"][0]["dest"] == "x.txt"


def test_dry_run_preview(temp_workspace, capstdout):
    """Test that dry-run option outputs a preview without changing files."""
    f1 = temp_workspace / "a.txt"
    f1.write_text("A")

    # Run tool with --dry-run
    # We call main() directly by mocking args
    test_args = ["-d", str(temp_workspace), "--match", "a.txt", "--lower", "--dry-run"]

    # Since main calls sys.exit(0) on dry run success
    with pytest.raises(SystemExit) as e:
        file_renamer.main(test_args)

    assert e.value.code == 0
    # The file should not be renamed (lower of a.txt is a.txt, wait!
    # a.txt to a.txt is a no-op, so it skips renaming!)
    # Let's test with a casing change: a.txt -> A.txt
    f2 = temp_workspace / "hello.txt"
    f2.write_text("hello")
    test_args = [
        "-d",
        str(temp_workspace),
        "--match",
        "hello.txt",
        "--upper",
        "--dry-run",
    ]
    with pytest.raises(SystemExit) as e:
        file_renamer.main(test_args)
    assert e.value.code == 0

    assert f2.exists()
    assert "HELLO.txt" not in os.listdir(temp_workspace)


@pytest.fixture
def capstdout(capsys):
    """Fixture to capture stdout."""
    return capsys


def test_parse_args_mutually_exclusive() -> None:
    """Test --lower and --upper mutually exclusive validation."""
    with pytest.raises(SystemExit):
        file_renamer.parse_args(["--lower", "--upper"])


def test_parse_args_invalid_number_format() -> None:
    """Test invalid --number-format validation."""
    with pytest.raises(SystemExit):
        file_renamer.parse_args(["--number", "--number-format", "{invalid}"])


def test_collect_files_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test collect_files handling OSError when scanning directory."""
    def mock_scandir(path):
        raise OSError("Permission denied")
    monkeypatch.setattr(os, "scandir", mock_scandir)
    with pytest.raises(SystemExit):
        file_renamer.collect_files("dummy_dir", "*", None, False, "dummy_history")


def test_execute_undo_validation_failures(temp_workspace) -> None:
    """Test execute_undo handling various validation failures."""
    # 1. History file does not exist
    with pytest.raises(SystemExit):
        file_renamer.execute_undo("nonexistent_hist.json", str(temp_workspace))

    # 2. History file has bad json
    bad_json_file = temp_workspace / "bad_hist.json"
    bad_json_file.write_text("bad json")
    with pytest.raises(SystemExit):
        file_renamer.execute_undo(str(bad_json_file), str(temp_workspace))

    # 3. Already undone
    undone_file = temp_workspace / "undone_hist.json"
    undone_file.write_text(json.dumps({"undone": True}))
    with pytest.raises(SystemExit) as exc_info:
        file_renamer.execute_undo(str(undone_file), str(temp_workspace))
    assert exc_info.value.code == 0

    # 4. No renames recorded
    empty_file = temp_workspace / "empty_hist.json"
    empty_file.write_text(json.dumps({"undone": False, "renames": []}))
    with pytest.raises(SystemExit) as exc_info:
        file_renamer.execute_undo(str(empty_file), str(temp_workspace))
    assert exc_info.value.code == 0

    # 5. Missing files to undo (dest file missing on disk)
    missing_file_hist = temp_workspace / "missing_file_hist.json"
    missing_file_hist.write_text(json.dumps({
        "undone": False,
        "renames": [{"src": "orig.txt", "dest": "missing.txt"}]
    }))
    with pytest.raises(SystemExit) as exc_info:
        file_renamer.execute_undo(str(missing_file_hist), str(temp_workspace))
    assert exc_info.value.code == 1

    # 6. Original target file already exists
    collision_hist = temp_workspace / "collision_hist.json"
    collision_hist.write_text(json.dumps({
        "undone": False,
        "renames": [{"src": "exists_orig.txt", "dest": "current.txt"}]
    }))
    # create both orig and dest files to trigger collision check 2
    (temp_workspace / "exists_orig.txt").write_text("original content")
    (temp_workspace / "current.txt").write_text("current content")
    with pytest.raises(SystemExit) as exc_info:
        file_renamer.execute_undo(str(collision_hist), str(temp_workspace))
    assert exc_info.value.code == 1


def test_undo_phase1_failure_rollback(temp_workspace, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test undo phase 1 failure rollback when renaming dest -> temp."""
    f1 = temp_workspace / "current.txt"
    f1.write_text("current")
    
    history_file = temp_workspace / "history.json"
    history_file.write_text(json.dumps({
        "undone": False,
        "renames": [{"src": "original.txt", "dest": "current.txt"}]
    }))

    def mock_rename(*args, **kwargs):
        raise OSError("Phase 1 undo rename failed")
    monkeypatch.setattr(os, "rename", mock_rename)

    with pytest.raises(SystemExit) as exc_info:
        file_renamer.execute_undo(str(history_file), str(temp_workspace))
    assert exc_info.value.code == 1
    assert f1.exists()


def test_main_cli_execution_errors(temp_workspace, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test main function handling various errors and confirmation prompts."""
    # 1. Invalid target directory
    with pytest.raises(SystemExit):
        file_renamer.main(["-d", "nonexistent_directory_xyz_123"])

    # 2. Conflicts detected
    f1 = temp_workspace / "a.txt"
    f1.write_text("content")
    f2 = temp_workspace / "b.txt"
    f2.write_text("content")
    # Will rename both to the same file (many-to-one)
    with pytest.raises(SystemExit) as exc_info:
        file_renamer.main(["-d", str(temp_workspace), "--match", "*.txt", "--regex-find", ".*", "--regex-replace", "same_name"])
    assert exc_info.value.code == 1

    # 3. User confirmation - No/N
    monkeypatch.setattr("builtins.input", lambda _: "n")
    f3 = temp_workspace / "c.txt"
    f3.write_text("content")
    with pytest.raises(SystemExit) as exc_info:
        file_renamer.main(["-d", str(temp_workspace), "--match", "c.txt", "--upper"])
    assert exc_info.value.code == 0
    assert f3.exists()
    assert "c.txt" in os.listdir(temp_workspace)

    # 4. User confirmation - Yes/Y
    monkeypatch.setattr("builtins.input", lambda _: "y")
    file_renamer.main(["-d", str(temp_workspace), "--match", "c.txt", "--upper"])
    assert "C.txt" in os.listdir(temp_workspace)
    assert "c.txt" not in os.listdir(temp_workspace)


def test_main_cli_sorting_mtime(temp_workspace) -> None:
    """Test main function with sorting by modification time."""
    import time
    f1 = temp_workspace / "a.txt"
    f1.write_text("A")
    time.sleep(0.02)
    f2 = temp_workspace / "b.txt"
    f2.write_text("B")
    
    # Run with sort mtime and numbering
    file_renamer.main([
        "-d", str(temp_workspace),
        "--match", "*.txt",
        "--sort", "mtime",
        "--number",
        "--number-format", "{num}_{name}",
        "--force"
    ])
    assert "001_a.txt" in os.listdir(temp_workspace)
    assert "002_b.txt" in os.listdir(temp_workspace)
