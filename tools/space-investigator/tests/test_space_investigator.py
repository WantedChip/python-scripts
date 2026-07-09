"""Tests for space_investigator.py."""

# pylint: disable=wrong-import-position,import-error,missing-class-docstring
# pylint: disable=missing-function-docstring,unused-import
import csv
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from space_investigator import (  # noqa: E402
    DirectoryEntry,
    FileEntry,
    ScanResult,
    export_report,
    human_readable,
    main,
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
        result = scan_directory(
            str(tmp_path), top_n=10, large_file_mb=1.0, exclude_dirs=()
        )
        assert result.total_bytes == 3000
        assert result.total_files == 2

    def test_top_files_sorted_desc(self, tmp_path: Path) -> None:
        self._make_file(tmp_path / "small.txt", 100)
        self._make_file(tmp_path / "big.txt", 10000)
        result = scan_directory(
            str(tmp_path), top_n=10, large_file_mb=1.0, exclude_dirs=()
        )
        assert result.top_files[0].size_bytes == 10000

    def test_large_files_threshold(self, tmp_path: Path) -> None:
        self._make_file(tmp_path / "normal.txt", 100)
        self._make_file(tmp_path / "huge.bin", 200 * 1024 * 1024)  # 200 MB
        result = scan_directory(
            str(tmp_path), top_n=10, large_file_mb=100.0, exclude_dirs=()
        )
        large_paths = [f.path for f in result.large_files]
        assert any("huge.bin" in p for p in large_paths)
        assert all("normal.txt" not in p for p in large_paths)

    def test_exclude_dirs(self, tmp_path: Path) -> None:
        excluded = tmp_path / "excluded_dir"
        excluded.mkdir()
        self._make_file(excluded / "secret.txt", 5000)
        result = scan_directory(
            str(tmp_path), top_n=10, large_file_mb=1.0, exclude_dirs=("excluded_dir",)
        )
        assert result.total_files == 0

    def test_extension_breakdown(self, tmp_path: Path) -> None:
        self._make_file(tmp_path / "a.py", 500)
        self._make_file(tmp_path / "b.py", 300)
        self._make_file(tmp_path / "c.txt", 200)
        result = scan_directory(
            str(tmp_path), top_n=10, large_file_mb=1.0, exclude_dirs=()
        )
        assert ".py" in result.extension_breakdown
        assert result.extension_breakdown[".py"] == 800

    def test_recursive_scan(self, tmp_path: Path) -> None:
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        self._make_file(subdir / "nested.txt", 1234)
        result = scan_directory(
            str(tmp_path), top_n=10, large_file_mb=1.0, exclude_dirs=()
        )
        assert result.total_files == 1
        assert result.total_bytes == 1234

    def test_top_n_limit(self, tmp_path: Path) -> None:
        for i in range(15):
            self._make_file(tmp_path / f"file_{i:02d}.txt", (i + 1) * 100)
        result = scan_directory(
            str(tmp_path), top_n=5, large_file_mb=1.0, exclude_dirs=()
        )
        assert len(result.top_files) == 5


# ---------------------------------------------------------------------------
# Additional coverage tests
# ---------------------------------------------------------------------------


def test_scan_directory_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test scan_directory logs a warning and skips files failing os.getsize."""
    f = tmp_path / "test.txt"
    f.touch()

    # Force os.getsize to raise OSError
    def mock_getsize(path: str) -> int:
        raise OSError("Permission denied")

    monkeypatch.setattr(os.path, "getsize", mock_getsize)

    result = scan_directory(str(tmp_path), top_n=10, large_file_mb=1.0, exclude_dirs=())
    assert result.total_files == 0
    assert result.total_bytes == 0


def test_export_report_formats(tmp_path: Path) -> None:
    """Test exporting reports in different file formats (json, csv, txt)."""
    res = ScanResult(
        root=str(tmp_path),
        total_bytes=1000,
        total_files=2,
        top_files=[FileEntry("a.txt", 600), FileEntry("b.txt", 400)],
        top_dirs=[DirectoryEntry("sub", 1000, 2)],
        large_files=[FileEntry("a.txt", 600)],
        extension_breakdown={".txt": 1000},
    )

    # 1. JSON
    json_path = tmp_path / "report.json"
    export_report(res, str(json_path), "json")
    with open(json_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["total_bytes"] == 1000
    assert len(data["top_files"]) == 2

    # 2. CSV
    csv_path = tmp_path / "report.csv"
    export_report(res, str(csv_path), "csv")
    with open(csv_path, "r", newline="", encoding="utf-8") as fh:
        reader = list(csv.DictReader(fh))
    assert len(reader) == 3
    assert reader[0]["path"] == "a.txt"

    # 3. TXT
    txt_path = tmp_path / "report.txt"
    export_report(res, str(txt_path), "txt")
    txt_content = txt_path.read_text(encoding="utf-8")
    assert "Root:" in txt_content
    assert "a.txt" in txt_content

    # 4. Invalid format should not create a file
    bad_path = tmp_path / "report.bad"
    export_report(res, str(bad_path), "invalid_format")
    assert not bad_path.exists()


def test_main_cli_execution(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI parsing and execution logic."""
    # 1. Nonexistent directory exits 1
    with pytest.raises(SystemExit) as exc_info:
        main(["--root", "nonexistent_directory_123_abc"])
    assert exc_info.value.code == 1

    # 2. Valid directory runs scanning and prints report
    f = tmp_path / "a.py"
    f.write_text("print('hello')")

    out_json = tmp_path / "out.json"
    main(["--root", str(tmp_path), "--output", str(out_json), "--format", "json"])

    assert out_json.exists()
    captured = capsys.readouterr()
    assert "Disk Space Investigator" in captured.out
