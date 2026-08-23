import contextlib
import csv
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, List, Tuple
from unittest.mock import patch

from main import (
    DuplicateGroup,
    build_parser,
    calculate_file_hash,
    export_csv_report,
    export_json_report,
    find_duplicates,
    format_bytes,
    generate_console_report,
    main,
    process_deletion,
    process_quarantine,
)


def _run_cli(args: List[str]) -> Any:
    """Runs ``main`` with redirected stdout/stdin; returns (code, output)."""
    out_buf = io.StringIO()
    with contextlib.redirect_stdout(out_buf):
        exit_code = main(args)
    return exit_code, out_buf.getvalue()


class TestDuplicateFileFinder(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_find_duplicates(self):
        content_a = b"Exact duplicate content for testing."
        content_b = b"Different content altogether."

        f1 = self.test_dir / "file1.txt"
        f2 = self.test_dir / "sub" / "file2.txt"
        f3 = self.test_dir / "unique.txt"

        f2.parent.mkdir(parents=True, exist_ok=True)

        f1.write_bytes(content_a)
        f2.write_bytes(content_a)
        f3.write_bytes(content_b)

        groups = find_duplicates(self.test_dir)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0].files), 2)
        self.assertEqual(groups[0].file_size, len(content_a))

    def test_export_json_and_csv(self):
        f1 = self.test_dir / "a.txt"
        f2 = self.test_dir / "b.txt"
        f1.write_text("duplicate text")
        f2.write_text("duplicate text")

        groups = find_duplicates(self.test_dir)

        json_file = self.test_dir / "report.json"
        csv_file = self.test_dir / "report.csv"

        export_json_report(groups, json_file)
        export_csv_report(groups, csv_file)

        self.assertTrue(json_file.exists())
        with open(json_file, "r") as f:
            data = json.load(f)
            self.assertEqual(data["summary"]["group_count"], 1)

        self.assertTrue(csv_file.exists())
        with open(csv_file, "r") as f:
            reader = list(csv.reader(f))
            self.assertEqual(len(reader), 3)  # Header + original + duplicate

    def test_quarantine_duplicates(self):
        f1 = self.test_dir / "orig.bin"
        f2 = self.test_dir / "copy.bin"
        f1.write_bytes(b"1234567890")
        f2.write_bytes(b"1234567890")

        groups = find_duplicates(self.test_dir)
        q_dir = self.test_dir / "quarantine"

        moved = process_quarantine(groups, q_dir, dry_run=False)
        self.assertEqual(len(moved), 1)
        # The group original is the deterministically-first path (shortest,
        # then alphabetical): copy.bin. Only that file must survive.
        self.assertTrue(f2.exists())
        self.assertFalse(f1.exists())
        self.assertTrue((q_dir / "orig.bin").exists())

    def test_delete_duplicates(self):
        f1 = self.test_dir / "orig.bin"
        f2 = self.test_dir / "copy.bin"
        f1.write_bytes(b"1234567890")
        f2.write_bytes(b"1234567890")

        groups = find_duplicates(self.test_dir)
        deleted = process_deletion(groups, dry_run=False)

        self.assertEqual(len(deleted), 1)
        # The group original is the deterministically-first path (shortest,
        # then alphabetical): copy.bin. Only that file must survive.
        self.assertTrue(f2.exists())
        self.assertFalse(f1.exists())


class TestFindDuplicatesStages(unittest.TestCase):
    """Multi-stage detection: min-size filter, excludes, and validation."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.dir_path = Path(self.temp_dir.name)

    def _make_pair(self, content: bytes, names: Tuple[str, str]) -> None:
        """Writes two identical files with the given names."""
        for name in names:
            (self.dir_path / name).write_bytes(content)

    def test_min_size_filters_out_small_files(self) -> None:
        self._make_pair(b"tiny", ("t1.txt", "t2.txt"))
        self.assertEqual(find_duplicates(self.dir_path, min_size=100), [])

    def test_exclude_patterns_skip_matching_filenames(self) -> None:
        self._make_pair(b"same bytes", ("keep.txt", "skipme.txt"))
        groups = find_duplicates(self.dir_path, exclude_patterns=["skipme", ".cache"])
        self.assertEqual(groups, [])

    def test_nonexistent_directory_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            find_duplicates(self.dir_path / "missing")

    def test_same_size_same_head_different_tail_not_duplicate(self) -> None:
        """Files sharing size+4KB head but differing later are distinct."""
        (self.dir_path / "x1.bin").write_bytes(b"A" * 9000 + b"tail-one")
        (self.dir_path / "x2.bin").write_bytes(b"A" * 9000 + b"tail-two")
        self.assertEqual(find_duplicates(self.dir_path), [])

    def test_partial_hash_reads_only_requested_prefix(self) -> None:
        """A partial hash of N bytes equals the full hash of those N bytes."""
        path = self.dir_path / "blob.bin"
        path.write_bytes(b"prefix-" + b"x" * 20000)
        prefix_file = self.dir_path / "prefix.bin"
        prefix_file.write_bytes(b"prefix-")
        partial = calculate_file_hash(path, partial_bytes=7)
        self.assertEqual(partial, calculate_file_hash(prefix_file))
        self.assertNotEqual(partial, calculate_file_hash(path))


class TestReportingHelpers(unittest.TestCase):
    """Console report rendering and byte formatting."""

    def setUp(self) -> None:
        self.group = DuplicateGroup(
            hash_val="a" * 64,
            file_size=2048,
            files=[Path("/r/orig.txt"), Path("/r/dup.txt")],
        )

    def test_format_bytes_units(self) -> None:
        self.assertEqual(format_bytes(512), "512 B")
        self.assertEqual(format_bytes(1024), "1.00 KB")
        self.assertEqual(format_bytes(5 * 1024 * 1024), "5.00 MB")

    def test_console_report_empty_case(self) -> None:
        self.assertEqual(generate_console_report([]), "No duplicate files found.")

    def test_console_report_lists_original_and_duplicates(self) -> None:
        report = generate_console_report([self.group])
        self.assertIn("Found 1 duplicate group(s) containing 2 files.", report)
        self.assertIn("Estimated space saveable: 2.00 KB", report)
        self.assertIn(f"[Original]   : {Path('/r/orig.txt')}", report)
        self.assertIn(f"[Duplicate]  : {Path('/r/dup.txt')}", report)
        self.assertIn("Hash: aaaaaaaaaaaa...", report)

    def test_format_bytes_petabyte_fallback(self) -> None:
        pb = 1024**5
        self.assertEqual(format_bytes(pb * 2), "2.00 PB")


class TestQuarantineDryRunAndCollisions(unittest.TestCase):
    """Quarantine planning without execution and name collision handling."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.dir_path = Path(self.temp_dir.name)
        (self.dir_path / "one.dat").write_bytes(b"duplicate-data")
        (self.dir_path / "two.dat").write_bytes(b"duplicate-data")
        self.groups = find_duplicates(self.dir_path)

    def test_dry_run_plans_moves_without_touching_files(self) -> None:
        actions = process_quarantine(self.groups, self.dir_path / "q", dry_run=True)
        self.assertEqual(len(actions), 1)
        src, dst = actions[0]
        self.assertTrue(src.exists())
        self.assertFalse(dst.exists())
        self.assertFalse((self.dir_path / "q").exists())
        self.assertEqual(len(find_duplicates(self.dir_path)), 1)

    def test_name_collision_gets_counter_suffix(self) -> None:
        q_dir = self.dir_path / "q"
        moved_name = self.groups[0].files[1].name
        (q_dir := self.dir_path / "q").mkdir()
        (q_dir / moved_name).write_bytes("occupied".encode())
        process_quarantine(self.groups, q_dir, dry_run=False)
        quarantined = sorted(p.name for p in q_dir.iterdir())
        self.assertIn(moved_name, quarantined)
        self.assertTrue(any(n != moved_name for n in quarantined))


class TestDeletionDryRun(unittest.TestCase):
    """Deletion dry-run must not remove anything."""

    def test_dry_run_reports_without_unlinking(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        dir_path = Path(temp_dir.name)
        (dir_path / "f1.txt").write_bytes(b"same-content")
        (dir_path / "f2.txt").write_bytes(b"same-content")
        groups = find_duplicates(dir_path)
        planned = process_deletion(groups, dry_run=True)
        self.assertEqual(len(planned), 1)
        self.assertTrue((dir_path / "f1.txt").exists())
        self.assertTrue((dir_path / "f2.txt").exists())


class TestCliEntrypoint(unittest.TestCase):
    """End-to-end CLI runs against temporary directories."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.dir_path = Path(self.temp_dir.name)
        (self.dir_path / "a.log").write_bytes(b"log-line-123456")
        (self.dir_path / "b.log").write_bytes(b"log-line-123456")

    def test_scan_prints_group_and_exports_reports(self) -> None:
        json_path = self.dir_path / "out.json"
        csv_path = self.dir_path / "out.csv"
        code, out = _run_cli(
            [
                "--dir",
                str(self.dir_path),
                "--json",
                str(json_path),
                "--csv",
                str(csv_path),
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn("[Original]", out)
        self.assertIn(f"Exported JSON report to '{json_path}'.", out)
        self.assertIn(f"Exported CSV report to '{csv_path}'.", out)
        data = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(data["summary"]["total_wasted_bytes"], 15)
        rows = list(csv.reader(csv_path.read_text(encoding="utf-8").splitlines()))
        self.assertEqual(
            rows[0], ["group_id", "hash", "file_size_bytes", "role", "file_path"]
        )

    def test_no_duplicates_message_when_clean(self) -> None:
        clean_dir = self.dir_path / "clean"
        clean_dir.mkdir()
        (clean_dir / "only.txt").write_bytes(b"unique")
        code, out = _run_cli(["--dir", str(clean_dir)])
        self.assertEqual(code, 0)
        self.assertIn("No duplicate files found.", out)

    def test_delete_dry_run_does_not_remove_files(self) -> None:
        code, out = _run_cli(["--dir", str(self.dir_path), "--delete"])
        self.assertEqual(code, 0)
        self.assertIn("[DRY RUN] Would delete duplicate files.", out)
        self.assertTrue((self.dir_path / "a.log").exists())
        self.assertTrue((self.dir_path / "b.log").exists())

    def test_cli_quarantine_without_apply_prints_dry_run(self) -> None:
        q_dir = self.dir_path / "q"
        code, out = _run_cli(["--dir", str(self.dir_path), "--quarantine", str(q_dir)])
        self.assertEqual(code, 0)
        self.assertIn("[DRY RUN] Would move duplicate files to quarantine", out)
        self.assertIn("--apply to execute", out)

    def test_quarantine_with_apply_and_yes_moves_files(self) -> None:
        q_dir = self.dir_path / "q"
        code, out = _run_cli(
            [
                "--dir",
                str(self.dir_path),
                "--quarantine",
                str(q_dir),
                "--apply",
                "--yes",
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn("Quarantined 1 duplicate file(s)", out)
        self.assertFalse((self.dir_path / "b.log").exists())
        self.assertTrue((q_dir / "b.log").exists())

    @patch("builtins.input", return_value="n")
    def test_quarantine_confirmation_declined_cancels(self, mock_input: Any) -> None:
        q_dir = self.dir_path / "q"
        code, out = _run_cli(
            [
                "--dir",
                str(self.dir_path),
                "--quarantine",
                str(q_dir),
                "--apply",
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn("Quarantine operation cancelled.", out)
        mock_input.assert_called_once()
        self.assertTrue((self.dir_path / "b.log").exists())

    @patch("builtins.input", return_value="y")
    def test_delete_confirmation_accepted_deletes(self, mock_input: Any) -> None:
        code, out = _run_cli(["--dir", str(self.dir_path), "--delete", "--apply"])
        self.assertEqual(code, 0)
        self.assertIn("Permanently deleted 1 duplicate file(s).", out)
        mock_input.assert_called_once()

    @patch("builtins.input", return_value="n")
    def test_delete_confirmation_declined_keeps_files(self, mock_input: Any) -> None:
        code, out = _run_cli(["--dir", str(self.dir_path), "--delete", "--apply"])
        self.assertEqual(code, 0)
        self.assertIn("Deletion operation cancelled.", out)
        self.assertTrue((self.dir_path / "b.log").exists())

    def test_parser_accepts_short_flags(self) -> None:
        parser = build_parser()
        parsed = parser.parse_args(["-d", "somedir", "--min-size", "10", "-y"])
        self.assertEqual(parsed.dir, "somedir")
        self.assertEqual(parsed.min_size, 10)
        self.assertTrue(parsed.yes)
        self.assertFalse(parsed.apply)


if __name__ == "__main__":
    unittest.main()
