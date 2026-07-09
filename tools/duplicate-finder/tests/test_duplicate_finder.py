"""Tests for Duplicate File Finder."""

import hashlib
import sys
import time
from pathlib import Path

# Ensure the parent folder is in path for imports to resolve.
sys.path.insert(0, str(Path(__file__).parent.parent))

# pylint: disable=wrong-import-position,import-error
import pytest  # noqa: E402
from duplicate_finder import (  # noqa: E402
    calculate_hash,
    find_duplicates,
    format_size,
    quarantine_duplicates,
    scan_directories,
    should_exclude,
)


def test_format_size() -> None:
    """Tests the format_size function with various inputs."""
    assert format_size(500) == "500 B"
    assert format_size(1024) == "1.00 KB"
    assert format_size(1024 * 1024) == "1.00 MB"
    assert format_size(1024 * 1024 * 1024 * 1.5) == "1.50 GB"
    assert format_size(1024 * 1024 * 1024 * 1024 * 1024 * 2.5) == "2.50 PB"


def test_calculate_hash(tmp_path: Path) -> None:
    """Tests calculate_hash on a test file with different algorithms."""
    test_file = tmp_path / "test.txt"
    content = b"hello world"
    test_file.write_bytes(content)

    assert calculate_hash(test_file, "md5") == hashlib.md5(content).hexdigest()
    assert calculate_hash(test_file, "sha256") == hashlib.sha256(content).hexdigest()
    assert calculate_hash(test_file, "sha1") == hashlib.sha1(content).hexdigest()

    with pytest.raises(ValueError):
        calculate_hash(test_file, "invalid_algo")


def test_should_exclude() -> None:
    """Tests path exclusion pattern matching."""
    assert should_exclude(Path("dir/subdir/.git"), [".git"]) is True
    assert should_exclude(Path("dir/subdir/foo.pyc"), ["*.pyc"]) is True
    assert should_exclude(Path(".venv/bin/python"), [".venv"]) is True
    assert should_exclude(Path("src/main.py"), [".venv", ".git"]) is False
    assert should_exclude(Path("src/main.py"), ["*main*"]) is True


def test_scan_directories(tmp_path: Path) -> None:
    """Tests scan_directories correctly filters by min_size, paths, and exclusions."""
    dir1 = tmp_path / "dir1"
    dir1.mkdir()

    f1 = dir1 / "file1.txt"
    f1.write_bytes(b"a" * 10)  # size 10

    f2 = dir1 / "file2.txt"
    f2.write_bytes(b"b" * 5)  # size 5

    sub = dir1 / "sub"
    sub.mkdir()
    f3 = sub / "file3.txt"
    f3.write_bytes(b"c" * 10)  # size 10

    # Excluded subdir
    ex_sub = dir1 / "exclude_me"
    ex_sub.mkdir()
    f4 = ex_sub / "file4.txt"
    f4.write_bytes(b"d" * 10)  # size 10

    # Scan with min_size = 0, no exclusions
    files_0 = scan_directories([dir1], min_size=0)
    assert len(files_0[10]) == 3
    assert len(files_0[5]) == 1
    assert f1.resolve() in files_0[10]
    assert f3.resolve() in files_0[10]
    assert f4.resolve() in files_0[10]
    assert f2.resolve() in files_0[5]

    # Scan with min_size = 8
    files_8 = scan_directories([dir1], min_size=8)
    assert 10 in files_8
    assert 5 not in files_8
    assert len(files_8[10]) == 3

    # Scan with exclusions
    files_ex = scan_directories([dir1], min_size=0, exclude_patterns=["*exclude_me*"])
    assert len(files_ex[10]) == 2
    assert f4.resolve() not in files_ex[10]


def test_find_duplicates_shortest_path(tmp_path: Path) -> None:
    """Tests find_duplicates with shortest-path strategy."""
    dir1 = tmp_path / "dir1"
    dir1.mkdir()

    # Create duplicates
    f1 = dir1 / "file1.txt"
    f1.write_bytes(b"duplicate_content")

    # Deeply nested duplicate (longer path)
    sub = dir1 / "sub"
    sub.mkdir()
    f2 = sub / "file2.txt"
    f2.write_bytes(b"duplicate_content")

    # Same folder duplicate (alphabetically sorted path will put file1.txt first)
    f3 = dir1 / "file1_dup.txt"
    f3.write_bytes(b"duplicate_content")

    files = scan_directories([dir1])
    groups, wasted = find_duplicates(
        files, hash_algo="sha256", strategy="shortest-path"
    )

    assert len(groups) == 1
    size, _, original, duplicates = groups[0]
    assert size == len(b"duplicate_content")
    assert original == f1.resolve()
    assert len(duplicates) == 2
    assert f2.resolve() in duplicates
    assert f3.resolve() in duplicates
    assert wasted == size * 2


def test_find_duplicates_time_strategies(tmp_path: Path) -> None:
    """Tests find_duplicates with oldest and newest strategies."""
    dir1 = tmp_path / "dir1"
    dir1.mkdir()

    f1 = dir1 / "f1.txt"
    f1.write_bytes(b"same_content")

    # Add artificial sleep to separate file creation times
    time.sleep(0.1)
    f2 = dir1 / "f2.txt"
    f2.write_bytes(b"same_content")

    time.sleep(0.1)
    f3 = dir1 / "f3.txt"
    f3.write_bytes(b"same_content")

    files = scan_directories([dir1])

    # Oldest strategy: f1.txt is original
    groups_old, _ = find_duplicates(files, strategy="oldest")
    assert groups_old[0][2] == f1.resolve()
    assert f2.resolve() in groups_old[0][3]
    assert f3.resolve() in groups_old[0][3]

    # Newest strategy: f3.txt is original
    groups_new, _ = find_duplicates(files, strategy="newest")
    assert groups_new[0][2] == f3.resolve()
    assert f1.resolve() in groups_new[0][3]
    assert f2.resolve() in groups_new[0][3]


def test_quarantine_duplicates(tmp_path: Path) -> None:
    """Tests moving duplicates to quarantine with relative paths and collisions."""
    scan_root = tmp_path / "scan"
    scan_root.mkdir()

    sub = scan_root / "sub"
    sub.mkdir()

    # Create duplicate files
    f1 = scan_root / "original.txt"
    f1.write_bytes(b"data")

    f2 = sub / "duplicate.txt"
    f2.write_bytes(b"data")

    # Create another duplicate file under main root
    f3 = scan_root / "duplicate.txt"
    f3.write_bytes(b"data")

    # Setup duplicate groups manually
    groups = [
        (
            4,
            "hash_val",
            f1.resolve(),
            [f2.resolve(), f3.resolve()],
        )
    ]

    quarantine_root = tmp_path / "quarantine"

    # Run dry run first
    moved_dry = quarantine_duplicates(
        groups, [scan_root], quarantine_root, dry_run=True
    )
    assert moved_dry == 2
    assert f2.exists()
    assert f3.exists()

    # Run actual quarantine
    moved_actual = quarantine_duplicates(
        groups, [scan_root], quarantine_root, dry_run=False
    )
    assert moved_actual == 2
    assert f1.exists()
    assert not f2.exists()
    assert not f3.exists()

    # f2 should go to: quarantine/sub/duplicate.txt
    target_f2 = quarantine_root / "sub" / "duplicate.txt"
    assert target_f2.exists()
    assert target_f2.read_bytes() == b"data"

    # f3 should go to: quarantine/duplicate.txt
    target_f3 = quarantine_root / "duplicate.txt"
    assert target_f3.exists()
    assert target_f3.read_bytes() == b"data"


def test_quarantine_collision(tmp_path: Path) -> None:
    """Tests that name collisions in quarantine are solved by adding suffix."""
    scan_root = tmp_path / "scan"
    scan_root.mkdir()

    f1 = scan_root / "original.txt"
    f1.write_bytes(b"data")

    f2 = scan_root / "duplicate.txt"
    f2.write_bytes(b"data")

    quarantine_root = tmp_path / "quarantine"
    quarantine_root.mkdir()

    # Pre-create duplicate.txt in quarantine to trigger collision
    existing_q_file = quarantine_root / "duplicate.txt"
    existing_q_file.write_bytes(b"existing_data")

    groups = [(4, "hash_val", f1.resolve(), [f2.resolve()])]

    moved = quarantine_duplicates(groups, [scan_root], quarantine_root, dry_run=False)
    assert moved == 1
    assert not f2.exists()

    # Should rename duplicate.txt to duplicate_1.txt
    renamed_file = quarantine_root / "duplicate_1.txt"
    assert renamed_file.exists()
    assert renamed_file.read_bytes() == b"data"
    # Original existing file is untouched
    assert existing_q_file.read_bytes() == b"existing_data"


def test_format_size_extreme() -> None:
    """Tests formatting very large size (ZB)."""
    assert format_size(1024**7) == "1024.00 ZB"


def test_scan_directories_nonexistent(caplog: pytest.LogCaptureFixture) -> None:
    """Tests scan_directories with a non-existent path."""
    import logging

    with caplog.at_level(logging.WARNING):
        res = scan_directories([Path("nonexistent_path_xyz")])
        assert not res
        assert "Path does not exist" in caplog.text


def test_scan_directories_exclude_input(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Tests scan_directories excluding the direct input path."""
    import logging

    f = tmp_path / "file.txt"
    f.touch()
    with caplog.at_level(logging.DEBUG):
        res = scan_directories([f], exclude_patterns=["*.txt"])
        assert not res
        assert "Excluding input path" in caplog.text


def test_scan_directories_single_file(tmp_path: Path) -> None:
    """Tests scan_directories with direct file paths."""
    f1 = tmp_path / "f1.txt"
    f1.write_bytes(b"hello")
    f2 = tmp_path / "f2.txt"
    f2.write_bytes(b"world")

    # Direct file scanning
    res = scan_directories([f1, f2], min_size=6)  # larger than actual size
    assert not res

    res = scan_directories([f1, f2], min_size=3)
    assert len(res[5]) == 2


def test_scan_directories_resolve_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tests scan_directories handling OSError during resolve/stat."""
    f = tmp_path / "f.txt"
    f.touch()

    def mock_resolve(*args, **kwargs):
        raise OSError("Access Denied")

    monkeypatch.setattr(Path, "resolve", mock_resolve)
    res = scan_directories([f])
    assert not res


def test_scan_directories_walk_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tests scan_directories handling OSError during directory walk file check."""
    dir1 = tmp_path / "dir1"
    dir1.mkdir()
    f1 = dir1 / "f1.txt"
    f1.touch()

    # Throw error when resolving path
    original_resolve = Path.resolve

    def mock_resolve(self, *args, **kwargs):
        if self.name == "f1.txt":
            raise OSError("Access Denied")
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", mock_resolve)
    res = scan_directories([dir1])
    assert not res


def test_find_duplicates_edge_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tests find_duplicates when files fails to hash or list length is 1."""
    # 1. Size group has <= 1 file
    res = find_duplicates({10: [Path("f1.txt")]})
    assert res == ([], 0)

    # 2. Hash function throws OSError
    f1 = tmp_path / "f1.txt"
    f1.write_bytes(b"data")
    f2 = tmp_path / "f2.txt"
    f2.write_bytes(b"data")

    def mock_calculate_hash(file_path, hash_algo="sha256", chunk_size=65536):
        raise OSError("Hash error")

    monkeypatch.setattr("duplicate_finder.calculate_hash", mock_calculate_hash)
    groups, wasted = find_duplicates({4: [f1, f2]})
    assert not groups
    assert wasted == 0


def test_quarantine_folder_creation_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tests quarantine_duplicates handling failure to create quarantine dir."""
    f1 = tmp_path / "f1.txt"
    f1.write_bytes(b"data")
    f2 = tmp_path / "f2.txt"
    f2.write_bytes(b"data")

    groups = [(4, "hash", f1, [f2])]

    def mock_mkdir(*args, **kwargs):
        raise OSError("Dir create error")

    monkeypatch.setattr(Path, "mkdir", mock_mkdir)
    res = quarantine_duplicates(groups, [tmp_path], tmp_path / "quarantine")
    assert res == 0


def test_quarantine_outside_roots(tmp_path: Path) -> None:
    """Tests quarantining duplicates that do not belong to any scan root."""
    scan_root = tmp_path / "scan"
    scan_root.mkdir()

    # f1 in scan_root, f2 is outside scan_root
    f1 = scan_root / "f1.txt"
    f1.write_bytes(b"data")
    f2 = tmp_path / "outside.txt"
    f2.write_bytes(b"data")

    groups = [(4, "hash", f1.resolve(), [f2.resolve()])]
    quarantine_root = tmp_path / "quarantine"

    moved = quarantine_duplicates(groups, [scan_root], quarantine_root, dry_run=False)
    assert moved == 1
    assert not f2.exists()
    assert (quarantine_root / "outside.txt").exists()


def test_quarantine_shutil_move_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tests quarantine_duplicates handling OSError during shutil.move."""
    f1 = tmp_path / "f1.txt"
    f1.write_bytes(b"data")
    f2 = tmp_path / "f2.txt"
    f2.write_bytes(b"data")

    groups = [(4, "hash", f1, [f2])]

    def mock_move(src, dst):
        raise OSError("Move error")

    monkeypatch.setattr("shutil.move", mock_move)
    moved = quarantine_duplicates(groups, [tmp_path], tmp_path / "quarantine")
    assert moved == 0


def test_main_cli_no_duplicates(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Tests the main function when no duplicates are found."""
    import duplicate_finder

    class DummyArgs:
        paths = [Path(".")]
        quarantine = None
        dry_run = False
        hash = "sha256"
        min_size = 0
        strategy = "shortest-path"
        exclude = []
        verbose = False

    monkeypatch.setattr(duplicate_finder, "parse_arguments", lambda: DummyArgs())
    monkeypatch.setattr(duplicate_finder, "scan_directories", lambda *a, **k: {})

    duplicate_finder.main()
    captured = capsys.readouterr()
    assert "No duplicate files found." in captured.out


def test_main_cli_with_duplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Tests the main function when duplicates are found and quarantined."""
    import duplicate_finder

    f1 = tmp_path / "f1.txt"
    f1.write_bytes(b"hello")
    f2 = tmp_path / "f2.txt"
    f2.write_bytes(b"hello")

    class DummyArgs:
        paths = [tmp_path]
        quarantine = tmp_path / "quarantine"
        dry_run = False
        hash = "sha256"
        min_size = 0
        strategy = "shortest-path"
        exclude = []
        verbose = True

    monkeypatch.setattr(duplicate_finder, "parse_arguments", lambda: DummyArgs())

    duplicate_finder.main()
    captured = capsys.readouterr()
    assert "Duplicate Files Report" in captured.out
    assert "Total duplicate groups: 1" in captured.out
    assert "Result: 1 of 1 duplicate files moved." in captured.out
