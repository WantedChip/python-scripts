"""Unit tests for filename-sanitizer."""

import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Tuple
from unittest.mock import patch

import main as fs_main
from main import build_parser, remove_diacritics, sanitize_directory, sanitize_filename


class TestFilenameSanitizer(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.target_dir = Path(self.temp_dir) / "files"
        self.target_dir.mkdir()

        self.file1 = self.target_dir / "Crème Brûlée 2023!.txt"
        self.file1.write_text("test", encoding="utf-8")

        # 'bad:name<test>?.pdf' cannot be used here: on Windows the colon
        # turns it into an NTFS alternate data stream named 'bad' instead of
        # a real directory entry. Use a whitespace-dirty name that is
        # creatable on every OS; illegal-character stripping is covered by
        # test_sanitize_filename_windows.
        self.file2 = self.target_dir / "bad   name   test.pdf"
        self.file2.write_text("test", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_remove_diacritics(self):
        self.assertEqual(remove_diacritics("Crème Brûlée"), "Creme Brulee")

    def test_sanitize_filename_windows(self):
        cleaned = sanitize_filename("bad:name<test>?.pdf", target_os="windows")
        self.assertEqual(cleaned, "badnametest.pdf")

    def test_sanitize_filename_options(self):
        cleaned = sanitize_filename(
            "Crème Brûlée.txt", space_replacement="-", lowercase=True
        )
        self.assertEqual(cleaned, "creme-brulee.txt")

    def test_sanitize_directory_dry_run(self):
        diffs = sanitize_directory(self.target_dir, dry_run=True)
        self.assertEqual(len(diffs), 2)
        self.assertTrue(self.file1.exists())

    def test_sanitize_directory_execute(self):
        diffs = sanitize_directory(self.target_dir, dry_run=False)
        self.assertEqual(len(diffs), 2)
        self.assertFalse(self.file1.exists())
        renamed_files = [f.name for f in self.target_dir.iterdir()]
        # '!' is not an illegal character, so it survives sanitization.
        self.assertIn("Creme_Brulee_2023!.txt", renamed_files)
        self.assertIn("bad_name_test.pdf", renamed_files)


class TestSanitizeFilenameRules(unittest.TestCase):
    """Character-class and naming rules of the pure sanitizer function."""

    def test_posix_illegal_characters_removed(self) -> None:
        """POSIX mode strips characters outside the Windows blacklist."""
        cleaned = sanitize_filename("na[me.txt", target_os="posix")
        self.assertEqual(cleaned, "name.txt")

    def test_windows_reserved_names_get_suffix(self) -> None:
        """Reserved device names are suffixed to stay creatable."""
        self.assertEqual(
            sanitize_filename("CON.txt", target_os="windows"), "CON_file.txt"
        )
        self.assertEqual(
            sanitize_filename("com1.dat", target_os="windows"), "com1_file.dat"
        )

    def test_fully_stripped_stem_becomes_unnamed(self) -> None:
        """A stem emptied by illegal-char stripping falls back to 'unnamed'."""
        cleaned = sanitize_filename("??? .txt", target_os="windows")
        self.assertEqual(cleaned, "unnamed.txt")

    def test_space_replacement_none_keeps_single_spaces(self) -> None:
        """'none' collapses whitespace runs instead of substituting."""
        cleaned = sanitize_filename("a  b   c.txt", space_replacement="none")
        self.assertEqual(cleaned, "a b c.txt")

    def test_dash_replacement_collapses_repeated_runs(self) -> None:
        """Runs of the replacement character collapse to one dash."""
        cleaned = sanitize_filename("a  -  b.txt", space_replacement="-")
        self.assertEqual(cleaned, "a-b.txt")


class TestSanitizeDirectoryOperations(unittest.TestCase):
    """Directory scans: recursion, collisions, and rename failures."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_dir, True)

    def test_recursive_mode_processes_subdirectories(self) -> None:
        """With recursive=True nested folders are sanitized too."""
        sub = self.temp_dir / "Nested Dir"
        sub.mkdir()
        (sub / "Ugly Name.txt").write_text("x", encoding="utf-8")

        report = sanitize_directory(self.temp_dir, recursive=True)

        renamed = [r["new_name"] for r in report]
        self.assertEqual(renamed, ["Ugly_Name.txt"])
        self.assertEqual([p.name for p in sub.iterdir()], ["Ugly_Name.txt"])

    def test_collision_with_existing_file_gets_numeric_suffix(self) -> None:
        """A rename colliding with a live file is suffixed _1, _2..."""
        # The two sources differ by more than case, so both can coexist on
        # a case-insensitive filesystem, yet both normalize to the same
        # target after diacritic stripping and lowercasing.
        (self.temp_dir / "Cafe Test.txt").write_text("x", encoding="utf-8")
        (self.temp_dir / "Café Test.txt").write_text("y", encoding="utf-8")

        report = sanitize_directory(self.temp_dir, lowercase=True)

        new_names = sorted(r["new_name"] for r in report)
        self.assertEqual(new_names, ["cafe_test.txt", "cafe_test_1.txt"])
        disk_names = {p.name for p in self.temp_dir.iterdir()}
        self.assertEqual(disk_names, {"cafe_test.txt", "cafe_test_1.txt"})

    def test_rename_failure_is_recorded_as_failed(self) -> None:
        """An OSError during rename is captured in the diff record."""
        (self.temp_dir / "Locked File.txt").write_text("x", encoding="utf-8")

        with patch.object(Path, "rename", side_effect=OSError(13, "denied")):
            report = sanitize_directory(self.temp_dir)

        self.assertEqual(len(report), 1)
        self.assertTrue(report[0]["status"].startswith("failed:"))
        self.assertEqual(report[0]["old_name"], "Locked File.txt")


class TestCommandLine(unittest.TestCase):
    """CLI flag parsing plus end-to-end runs on temporary trees."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_dir, True)

    def test_build_parser_flags_and_choices(self) -> None:
        """The parser exposes all documented flags and validates choices."""
        parser = build_parser()
        parsed = parser.parse_args(
            ["-p", str(self.temp_dir), "-s", "-", "-l", "-r", "--dry-run"]
        )
        self.assertEqual(parsed.space_replacement, "-")
        self.assertTrue(parsed.lowercase)
        self.assertTrue(parsed.recursive)
        self.assertTrue(parsed.dry_run)
        self.assertTrue(parsed.strip_diacritics)

        bad = build_parser()
        with self.assertRaises(SystemExit):
            bad.parse_args(["-p", "x", "-s", "+"])

    def _run_cli(self, *args: str) -> Tuple[int, str]:
        """Invoke main() capturing stdout; returns (code, output)."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = fs_main.main(list(args))
        return code, buf.getvalue()

    def test_main_dry_run_lists_proposed_changes(self) -> None:
        """Dry-run CLI reports each proposed rename without touching disk."""
        (self.temp_dir / "Messy Name.txt").write_text("x", encoding="utf-8")

        code, out = self._run_cli("-p", str(self.temp_dir), "--dry-run")

        self.assertEqual(code, 0)
        self.assertIn("[ dry_run ] Messy Name.txt -> Messy_Name.txt", out)
        self.assertTrue((self.temp_dir / "Messy Name.txt").exists())

    def test_main_executes_renames(self) -> None:
        """Without --dry-run the CLI performs and reports real renames."""
        (self.temp_dir / "Second Name.txt").write_text("x", encoding="utf-8")

        code, out = self._run_cli("-p", str(self.temp_dir))

        self.assertEqual(code, 0)
        self.assertIn("[ renamed ] Second Name.txt -> Second_Name.txt", out)
        self.assertEqual([p.name for p in self.temp_dir.iterdir()], ["Second_Name.txt"])


if __name__ == "__main__":
    unittest.main()
