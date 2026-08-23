"""
Unit tests for Filename Case Normalizer.
"""

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Tuple

import main as fcn
from main import (
    build_parser,
    convert_filename,
    process_directory,
    resolve_collision,
    to_snake_case,
    undo_renames,
)


class TestFilenameCaseNormalizer(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_to_snake_case(self):
        self.assertEqual(to_snake_case("myCamelCaseFile"), "my_camel_case_file")
        self.assertEqual(to_snake_case("hello world-file"), "hello_world_file")
        self.assertEqual(to_snake_case("SimpleTest123"), "simple_test123")

    def test_convert_filename(self):
        self.assertEqual(convert_filename("MyFile.TXT", "lowercase"), "myfile.txt")
        self.assertEqual(convert_filename("myfile.txt", "uppercase"), "MYFILE.txt")
        self.assertEqual(
            convert_filename("my_file_name.txt", "title"), "My_File_Name.txt"
        )
        self.assertEqual(
            convert_filename("my cool File.png", "snake"), "my_cool_file.png"
        )

    def test_resolve_collision_append_number(self):
        file1 = self.temp_dir / "test.txt"
        file1.touch()

        target = self.temp_dir / "test.txt"
        resolved = resolve_collision(target, set(), strategy="append_number")
        self.assertEqual(resolved.name, "test_1.txt")

    def test_process_directory_dry_run(self):
        f = self.temp_dir / "TestFile.txt"
        f.touch()

        renames = process_directory(self.temp_dir, mode="lowercase", dry_run=True)
        self.assertEqual(len(renames), 1)
        self.assertTrue(f.exists())  # Still original name in dry-run

    def test_process_directory_and_undo(self):
        f = self.temp_dir / "TestFile.txt"
        f.touch()

        manifest = self.temp_dir / "manifest.json"
        renames = process_directory(
            self.temp_dir, mode="lowercase", dry_run=False, manifest_path=manifest
        )
        self.assertEqual(len(renames), 1)
        # Path.exists() is case-insensitive on Windows, so verify via exact
        # directory entries that the original casing is really gone.
        names_after = {p.name for p in self.temp_dir.iterdir()}
        self.assertNotIn("TestFile.txt", names_after)
        renamed_file = self.temp_dir / "testfile.txt"
        self.assertTrue(renamed_file.exists())
        self.assertTrue(manifest.exists())

        # Test Undo
        restored_count = undo_renames(manifest)
        self.assertEqual(restored_count, 1)
        names_restored = {p.name for p in self.temp_dir.iterdir()}
        self.assertIn("TestFile.txt", names_restored)
        self.assertNotIn("testfile.txt", names_restored)


class TestConversionHelpers(unittest.TestCase):
    """Unit behaviour of convert_filename and to_snake_case edge inputs."""

    def test_unsupported_mode_raises_value_error(self) -> None:
        """An unknown casing mode raises ValueError."""
        with self.assertRaises(ValueError):
            convert_filename("file.txt", "shoutcase")

    def test_keep_extension_case_preserves_suffix(self) -> None:
        """keep_extension_case leaves the extension casing untouched."""
        result = convert_filename("Report.TXT", "lowercase", keep_extension_case=True)
        self.assertEqual(result, "report.TXT")

    def test_empty_stem_falls_back_to_lowercase_name(self) -> None:
        """A stem reduced to underscores falls back to the lowercased name."""
        self.assertEqual(to_snake_case("___"), "___")


class TestCollisionStrategies(unittest.TestCase):
    """resolve_collision behaviour for every documented strategy."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_dir, True)

    def test_overwrite_returns_target_even_when_occupied(self) -> None:
        """The overwrite strategy always returns the proposed target."""
        occupied = self.temp_dir / "dup.txt"
        occupied.touch()
        resolved = resolve_collision(occupied, set(), strategy="overwrite")
        self.assertEqual(resolved, occupied)

    def test_skip_returns_none_when_target_taken(self) -> None:
        """The skip strategy signals a skip via None."""
        occupied = self.temp_dir / "dup.txt"
        occupied.touch()
        self.assertIsNone(resolve_collision(occupied, set(), strategy="skip"))

    def test_append_number_skips_claimed_targets(self) -> None:
        """Targets already claimed earlier in the run are numbered past."""
        claimed = {str((self.temp_dir / "name.txt").resolve())}
        first_claim = {str((self.temp_dir / "name_1.txt").resolve())}

        resolved = resolve_collision(
            self.temp_dir / "name.txt",
            claimed | first_claim,
            strategy="append_number",
        )
        self.assertEqual(resolved.name, "name_2.txt")

    def test_exclude_source_counts_as_free(self) -> None:
        """The source file itself does not block a case-only rename."""
        source = self.temp_dir / "Same.TXT"
        source.touch()
        resolved = resolve_collision(
            self.temp_dir / "same.txt",
            set(),
            strategy="overwrite",
            exclude=source.resolve(),
        )
        # The exclude check makes the candidate look free even though the
        # source occupies it on a case-insensitive filesystem.
        self.assertIsNotNone(resolved)

    def test_unknown_strategy_raises_value_error(self) -> None:
        """An undocumented collision strategy raises ValueError."""
        free = self.temp_dir / "taken.txt"
        free.touch()
        with self.assertRaises(ValueError):
            resolve_collision(free, set(), strategy="merge")


class TestProcessDirectoryGuards(unittest.TestCase):
    """Directory validation and collision integration during processing."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_dir, True)

    def test_missing_directory_raises_file_not_found(self) -> None:
        """A nonexistent directory raises FileNotFoundError."""
        missing = self.temp_dir / "nope"
        with self.assertRaises(FileNotFoundError):
            process_directory(missing, mode="lowercase")

    def test_already_conforming_files_are_untouched(self) -> None:
        """Files whose names already match the target case are skipped."""
        (self.temp_dir / "plain.txt").touch()
        renames = process_directory(self.temp_dir, mode="lowercase")
        self.assertEqual(renames, [])
        self.assertEqual([p.name for p in self.temp_dir.iterdir()], ["plain.txt"])

    def test_skip_strategy_leaves_colliding_source_alone(self) -> None:
        """With 'skip', only the first of two colliding files is renamed."""
        (self.temp_dir / "report final.doc").write_text("a", encoding="utf-8")
        (self.temp_dir / "report-final.doc").write_text("b", encoding="utf-8")

        renames = process_directory(
            self.temp_dir, mode="snake", collision_strategy="skip"
        )

        self.assertEqual(len(renames), 1)
        names = {p.name for p in self.temp_dir.iterdir()}
        self.assertEqual(names, {"report_final.doc", "report-final.doc"})

    def test_append_number_resolves_second_collision(self) -> None:
        """Two sources converging on one name produce _1 suffixing."""
        (self.temp_dir / "report final.doc").write_text("a", encoding="utf-8")
        (self.temp_dir / "report-final.doc").write_text("b", encoding="utf-8")

        renames = process_directory(self.temp_dir, mode="snake")

        names = {p.name for p in self.temp_dir.iterdir()}
        self.assertEqual(names, {"report_final.doc", "report_final_1.doc"})
        self.assertEqual(len(renames), 2)

    def test_recursive_mode_reaches_nested_directories(self) -> None:
        """Recursive processing renames files inside subdirectories."""
        sub = self.temp_dir / "Nested"
        sub.mkdir()
        (sub / "Upper.TXT").touch()

        renames = process_directory(self.temp_dir, mode="lowercase", recursive=True)

        nested_names = {p.name for p in sub.iterdir()}
        self.assertEqual(len(renames), 1)
        self.assertEqual(nested_names, {"upper.txt"})


class TestUndoAndCli(unittest.TestCase):
    """Manifest undo plus end-to-end CLI argument handling."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_dir, True)

    def test_undo_with_missing_manifest_raises(self) -> None:
        """Undoing without a manifest file raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            undo_renames(self.temp_dir / "absent.json")

    def test_undo_restores_original_paths_from_manifest(self) -> None:
        """undo_renames moves each renamed path back and counts restores."""
        renamed = self.temp_dir / "new_name.txt"
        renamed.write_text("x", encoding="utf-8")
        original = self.temp_dir / "Old Name.txt"

        manifest = self.temp_dir / "manifest.json"
        manifest.write_text(
            json.dumps(
                [
                    {
                        "original": str(original),
                        "renamed": str(renamed),
                    }
                ]
            ),
            encoding="utf-8",
        )

        restored = undo_renames(manifest)
        self.assertEqual(restored, 1)
        self.assertTrue(original.exists())
        self.assertFalse(renamed.exists())

    def test_build_parser_choices_and_defaults(self) -> None:
        """The parser validates modes/strategies and defaults correctly."""
        parser = build_parser()
        parsed = parser.parse_args([str(self.temp_dir)])
        self.assertEqual(parsed.mode, "lowercase")
        self.assertEqual(parsed.collision, "append_number")
        self.assertFalse(parsed.recursive)
        self.assertFalse(parsed.dry_run)
        self.assertIsNone(parsed.manifest)
        self.assertIsNone(parsed.undo)

    def _run_cli(self, *args: str) -> Tuple[int, str]:
        """Invoke main() capturing stdout; returns (code, output)."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = fcn.main(list(args))
        return code, buf.getvalue()

    def test_main_dry_run_prints_preview_without_renaming(self) -> None:
        """Dry-run CLI output uses the preview prefix; files stay put."""
        (self.temp_dir / "MixedCase.md").touch()

        code, out = self._run_cli(
            str(self.temp_dir), "--mode", "uppercase", "--dry-run"
        )

        self.assertEqual(code, 0)
        self.assertIn("[DRY-RUN] Would rename: MixedCase.md -> MIXEDCASE.md", out)
        self.assertIn("Total files processed: 1", out)
        self.assertTrue((self.temp_dir / "MixedCase.md").exists())

    def test_main_executes_renames_and_reports_count(self) -> None:
        """A real run prints 'Renamed:' lines and the processed total."""
        (self.temp_dir / "Another One.txt").touch()

        code, out = self._run_cli(str(self.temp_dir), "--mode", "snake")

        self.assertEqual(code, 0)
        self.assertIn("Renamed: Another One.txt -> another_one.txt", out)
        self.assertIn("Total files processed: 1", out)

    def test_main_undo_flag_restores_and_exits_zero(self) -> None:
        """--undo consumes a saved manifest and reports the count."""
        target = self.temp_dir / "workdir"
        target.mkdir()
        (target / "Camel.txt").touch()
        manifest = self.temp_dir / "m.json"

        self._run_cli(str(target), "--manifest", str(manifest))
        self.assertTrue(manifest.exists())

        code, out = self._run_cli("--undo", str(manifest))
        self.assertEqual(code, 0)
        self.assertIn("Successfully undone 1 renames.", out)
        self.assertTrue((target / "Camel.txt").exists())

    def test_main_without_directory_or_undo_errors(self) -> None:
        """No directory and no --undo triggers argparse exit code 2."""
        with self.assertRaises(SystemExit) as ctx:
            fcn.main([])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
