"""Tests for space_investigator.py."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from space_investigator import (
    FileEntry,
    DirectoryEntry,
    ScanResult,
    human_readable,
    scan_directory,
)


# ---------------------------------------------------------------------------
# human_readable
# ---------------------------------------------------------------------------
class TestHumanReadable:
    def test_bytes(self) -> None:
        assert "B" in human_readable(500)

    def test_kilobytes(self) -> None:
        assert "KB" in human_readable(2048)

    def test_megabytes(self) -> None:
        assert "MB" in human_readable(2 * 1024 * 1024)

    def test_gigabytes(self) -> None:
        assert "GB" in human_readable(2 * 1024 * 1024 * 1024)

    def test_zero(self) -> None:
        result = human_readable(0)
        assert "0" in result


# ---------------------------------------------------------------------------
# scan_directory
# ---------------------------------------------------------------------------
class TestScanDirectory:
    def _make_file(self, path: Path, size: int) -> None:
        path.write_bytes(b"x" * size)

    def test_total_bytes(self, tmp_path: Path) -> None:
        self._make_file(tmp_path / "a.txt", 1000)
        self._make_file(tmp_path / "b.txt", 2000)
        result = scan_directory(str(tmp_path), top_n=10, large_file_mb=1.0, exclude_dirs=())
        assert result.total_bytes == 3000
        assert result.total_files == 2

    def test_top_files_sorted_desc(self, tmp_path: Path) -> None:
        self._make_file(tmp_path / "small.txt", 100)
        self._make_file(tmp_path / "big.txt", 10000)
        result = scan_directory(str(tmp_path), top_n=10, large_file_mb=1.0, exclude_dirs=())
        assert result.top_files[0].size_bytes == 10000

    def test_large_files_threshold(self, tmp_path: Path) -> None:
        self._make_file(tmp_path / "normal.txt", 100)
        self._make_file(tmp_path / "huge.bin", 200 * 1024 * 1024)  # 200 MB
        result = scan_directory(str(tmp_path), top_n=10, large_file_mb=100.0, exclude_dirs=())
        large_paths = [f.path for f in result.large_files]
        assert any("huge.bin" in p for p in large_paths)
        assert all("normal.txt" not in p for p in large_paths)

    def test_exclude_dirs(self, tmp_path: Path) -> None:
        excluded = tmp_path / "excluded_dir"
        excluded.mkdir()
        self._make_file(excluded / "secret.txt", 5000)
        result = scan_directory(str(tmp_path), top_n=10, large_file_mb=1.0,
                                exclude_dirs=("excluded_dir",))
        assert result.total_files == 0

    def test_extension_breakdown(self, tmp_path: Path) -> None:
        self._make_file(tmp_path / "a.py", 500)
        self._make_file(tmp_path / "b.py", 300)
        self._make_file(tmp_path / "c.txt", 200)
        result = scan_directory(str(tmp_path), top_n=10, large_file_mb=1.0, exclude_dirs=())
        assert ".py" in result.extension_breakdown
        assert result.extension_breakdown[".py"] == 800

    def test_recursive_scan(self, tmp_path: Path) -> None:
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        self._make_file(subdir / "nested.txt", 1234)
        result = scan_directory(str(tmp_path), top_n=10, large_file_mb=1.0, exclude_dirs=())
        assert result.total_files == 1
        assert result.total_bytes == 1234

    def test_top_n_limit(self, tmp_path: Path) -> None:
        for i in range(15):
            self._make_file(tmp_path / f"file_{i:02d}.txt", (i + 1) * 100)
        result = scan_directory(str(tmp_path), top_n=5, large_file_mb=1.0, exclude_dirs=())
        assert len(result.top_files) == 5
