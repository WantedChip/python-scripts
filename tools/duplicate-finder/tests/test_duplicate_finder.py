"""Tests for Duplicate File Finder."""

import hashlib
from pathlib import Path
import sys

# Ensure the parent folder is in path for imports to resolve.
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from duplicate_finder import (
    calculate_hash,
    find_duplicates,
    format_size,
    quarantine_duplicates,
    scan_directories,
)


def test_format_size() -> None:
    """Tests the format_size function with various inputs."""
    assert format_size(500) == "500 B"
    assert format_size(1024) == "1.00 KB"
    assert format_size(1024 * 1024) == "1.00 MB"
    assert format_size(1024 * 1024 * 1024 * 1.5) == "1.50 GB"


def test_calculate_hash(tmp_path: Path) -> None:
    """Tests calculate_hash on a test file with different algorithms."""
    test_file = tmp_path / "test.txt"
    content = b"hello world"
    test_file.write_bytes(content)

    assert calculate_hash(test_file, "md5") == hashlib.md5(content).hexdigest()
    assert (
        calculate_hash(test_file, "sha256")
        == hashlib.sha256(content).hexdigest()
    )
    assert (
        calculate_hash(test_file, "sha1") == hashlib.sha1(content).hexdigest()
    )


def test_scan_directories(tmp_path: Path) -> None:
    """Tests scan_directories correctly filters by min_size and paths."""
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

    # Scan with min_size = 0
    files_0 = scan_directories([dir1], min_size=0)
    assert len(files_0[10]) == 2
    assert len(files_0[5]) == 1
    assert f1.resolve() in files_0[10]
    assert f3.resolve() in files_0[10]
    assert f2.resolve() in files_0[5]

    # Scan with min_size = 8
    files_8 = scan_directories([dir1], min_size=8)
    assert 10 in files_8
    assert 5 not in files_8
    assert len(files_8[10]) == 2


def test_find_duplicates(tmp_path: Path) -> None:
    """Tests find_duplicates identifies original vs duplicates correctly."""
    dir1 = tmp_path / "dir1"
    dir1.mkdir()

    # Create duplicates
    f1 = dir1 / "file1.txt"
    f1.write_bytes(b"duplicate_content")

    # Deeply nested duplicate (should be duplicate, since it has longer path)
    sub = dir1 / "sub"
    sub.mkdir()
    f2 = sub / "file2.txt"
    f2.write_bytes(b"duplicate_content")

    # Same folder duplicate (alphabetically sorted path will put file1.txt first)
    f3 = dir1 / "file1_dup.txt"
    f3.write_bytes(b"duplicate_content")

    # Unique file
    f4 = dir1 / "unique.txt"
    f4.write_bytes(b"unique_content")

    files = scan_directories([dir1])
    groups, wasted = find_duplicates(files, hash_algo="sha256")

    assert len(groups) == 1
    size, file_hash, original, duplicates = groups[0]
    assert size == len(b"duplicate_content")
    assert file_hash == hashlib.sha256(b"duplicate_content").hexdigest()

    # Original should be the shortest path/alphabetical first:
    # str(f1) = .../dir1/file1.txt (len shorter than file1_dup.txt and sub/file2.txt)
    assert original == f1.resolve()

    assert len(duplicates) == 2
    assert f2.resolve() in duplicates
    assert f3.resolve() in duplicates
    assert wasted == size * 2


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

    # Setup duplicate groups manually for testing
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

    moved = quarantine_duplicates(
        groups, [scan_root], quarantine_root, dry_run=False
    )
    assert moved == 1
    assert not f2.exists()

    # Should rename duplicate.txt to duplicate_1.txt
    renamed_file = quarantine_root / "duplicate_1.txt"
    assert renamed_file.exists()
    assert renamed_file.read_bytes() == b"data"
    # Original existing file is untouched
    assert existing_q_file.read_bytes() == b"existing_data"
