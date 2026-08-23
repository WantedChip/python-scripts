import contextlib
import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, List
from unittest.mock import MagicMock, patch

from main import (
    RenamePlanItem,
    apply_case_format,
    build_rename_plan,
    check_collisions,
    execute_rename_plan,
    main,
    rollback_from_manifest,
)


def _run_cli(args: List[str]) -> Any:
    """Runs ``main`` capturing stdout/stderr/stdin; returns (code, out, err)."""
    out_buf, err_buf = io.StringIO(), io.StringIO()
    with (
        contextlib.redirect_stdout(out_buf),
        contextlib.redirect_stderr(err_buf),
    ):
        exit_code = main(args)
    return exit_code, out_buf.getvalue(), err_buf.getvalue()


class TestBulkFileRenamer(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_apply_case_format(self):
        self.assertEqual(apply_case_format("hello_world", "upper"), "HELLO_WORLD")
        self.assertEqual(apply_case_format("HELLO WORLD", "lower"), "hello world")
        self.assertEqual(apply_case_format("hello world", "title"), "Hello World")
        self.assertEqual(apply_case_format("Hello World", "snake"), "hello_world")
        self.assertEqual(apply_case_format("hello_world", "camel"), "helloWorld")

    def test_build_rename_plan_regex_and_numbering(self):
        f1 = self.test_dir / "img_001.png"
        f2 = self.test_dir / "img_002.png"
        f1.touch()
        f2.touch()

        plan = build_rename_plan(
            directory=self.test_dir,
            match_pattern=r"img_(\d+)",
            replace_pattern=r"photo_\1",
            prefix="vacation_",
            number_start=10,
            number_format="{:02d}",
        )

        matched_items = [p for p in plan if p.matched]
        self.assertEqual(len(matched_items), 2)
        self.assertEqual(matched_items[0].target.name, "vacation_photo_001_10.png")
        self.assertEqual(matched_items[1].target.name, "vacation_photo_002_11.png")

    def test_check_collisions(self):
        f1 = self.test_dir / "fileA.txt"
        f2 = self.test_dir / "fileB.txt"
        f1.touch()
        f2.touch()

        # Both mapping to fileC.txt
        plan = build_rename_plan(
            directory=self.test_dir,
            match_pattern=r"file[AB]\.txt",
            replace_pattern="fileC.txt",
        )

        collisions = check_collisions(plan)
        self.assertTrue(len(collisions) > 0)

    def test_execute_and_rollback(self):
        f1 = self.test_dir / "doc1.txt"
        f2 = self.test_dir / "doc2.txt"
        f1.write_text("content 1")
        f2.write_text("content 2")

        manifest_path = self.test_dir / "manifest.json"

        plan = build_rename_plan(
            directory=self.test_dir,
            match_pattern=r"doc(\d+)\.txt",
            replace_pattern=r"report_\1.txt",
        )

        executed = execute_rename_plan(plan, manifest_path=manifest_path)
        self.assertEqual(len(executed), 2)
        self.assertTrue((self.test_dir / "report_1.txt").exists())
        self.assertFalse(f1.exists())

        # Test Rollback
        restored = rollback_from_manifest(manifest_path)
        self.assertEqual(len(restored), 2)
        self.assertTrue(f1.exists())
        self.assertTrue(f2.exists())
        self.assertEqual(f1.read_text(), "content 1")


class TestApplyCaseFormatEdgeCases(unittest.TestCase):
    """Case formatting fallbacks and digit handling."""

    def test_none_and_empty_style_return_text_unchanged(self) -> None:
        self.assertEqual(apply_case_format("KeepMe", None), "KeepMe")
        self.assertEqual(apply_case_format("KeepMe", ""), "KeepMe")

    def test_unknown_style_returns_text_unchanged(self) -> None:
        self.assertEqual(apply_case_format("KeepMe", "shout"), "KeepMe")

    def test_snake_includes_digit_runs(self) -> None:
        self.assertEqual(
            apply_case_format("Report 2024 Final", "snake"),
            "report_2024_final",
        )

    def test_camel_joins_words_and_lowercases_first(self) -> None:
        self.assertEqual(apply_case_format("my test file", "camel"), "myTestFile")


class TestBuildRenamePlanRules(unittest.TestCase):
    """Plan construction rules: validation, scoping, and numbering."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.dir_path = Path(self.temp_dir.name)

    def test_missing_directory_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            build_rename_plan(directory=self.dir_path / "nope")

    def test_non_matching_files_are_skipped(self) -> None:
        (self.dir_path / "keep.log").write_text("x")
        (self.dir_path / "note.txt").write_text("x")
        plan = build_rename_plan(
            directory=self.dir_path,
            match_pattern=r"\.log$",
            replace_pattern=".txt",
        )
        # note.txt never matches the pattern so it is absent from the plan.
        self.assertEqual([i.source.name for i in plan], ["keep.log"])
        self.assertTrue(plan[0].matched)
        self.assertEqual(plan[0].target.name, "keep.txt")

    def test_recursive_flag_includes_nested_files(self) -> None:
        nested = self.dir_path / "sub"
        nested.mkdir()
        (nested / "deep_a.txt").write_text("x")
        (self.dir_path / "top_b.txt").write_text("x")
        flat_plan = build_rename_plan(directory=self.dir_path, match_pattern=r".*")
        deep_plan = build_rename_plan(
            directory=self.dir_path, match_pattern=r".*", recursive=True
        )
        flat_names = {i.source.name for i in flat_plan}
        deep_names = {i.source.name for i in deep_plan}
        self.assertNotIn("deep_a.txt", flat_names)
        self.assertIn("top_b.txt", flat_names)
        self.assertEqual(deep_names, {"deep_a.txt", "top_b.txt"})

    def test_numbering_honours_start_and_step(self) -> None:
        (self.dir_path / "s1.txt").write_text("x")
        (self.dir_path / "s2.txt").write_text("x")
        plan = build_rename_plan(
            directory=self.dir_path,
            match_pattern=r"s\d",
            replace_pattern="n",
            number_start=100,
            number_step=5,
        )
        numbers = [p.target.stem.rsplit("_", 1)[1] for p in plan if p.matched]
        self.assertEqual(numbers, ["100", "105"])

    def test_suffix_appended_to_stem(self) -> None:
        (self.dir_path / "base.md").write_text("x")
        plan = build_rename_plan(
            directory=self.dir_path,
            match_pattern=r"base",
            replace_pattern="base",
            suffix="_v2",
        )
        self.assertEqual(plan[0].target.name, "base_v2.md")


class TestCollisionAndExecutionFailures(unittest.TestCase):
    """Collision reporting and failed rename bookkeeping."""

    def test_target_existing_on_disk_reports_collision(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        dir_path = Path(temp_dir.name)
        (dir_path / "old.txt").write_text("a")
        (dir_path / "taken.txt").write_text("b")
        item = RenamePlanItem(
            source=dir_path / "old.txt",
            target=dir_path / "taken.txt",
            matched=True,
        )
        collisions = check_collisions([item])
        self.assertEqual(len(collisions), 1)
        self.assertIn("Target file exists: 'taken.txt'", collisions[0])

    def test_unmatched_items_are_ignored_by_collision_check(self) -> None:
        ghost = RenamePlanItem(
            source=Path("missing.txt"),
            target=Path("anything.txt"),
            matched=False,
        )
        self.assertEqual(check_collisions([ghost]), [])

    def test_failed_rename_marks_status_and_skips_manifest(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        dir_path = Path(temp_dir.name)
        manifest = dir_path / "m.json"
        bad_item = RenamePlanItem(
            source=dir_path / "ghost.txt",
            target=dir_path / "new.txt",
            matched=True,
        )
        executed = execute_rename_plan([bad_item], manifest_path=manifest)
        self.assertEqual(executed, [])
        self.assertTrue(bad_item.status.startswith("FAILED"))
        self.assertFalse(manifest.exists())

    def test_rollback_with_missing_manifest_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            rollback_from_manifest(Path("definitely_absent.json"))


class TestCliEntrypoint(unittest.TestCase):
    """End-to-end CLI runs inside an isolated temporary working dir."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.prev_cwd = Path.cwd()
        os.chdir(self.temp_dir.name)
        self.addCleanup(os.chdir, self.prev_cwd)

    def _seed_photos(self) -> None:
        Path("photo1.jpg").write_text("one")
        Path("photo2.jpg").write_text("two")

    def _rename_args(self, *extra: str) -> List[str]:
        return [
            "--dir",
            ".",
            "--match",
            r"photo(\d+)",
            "--replace",
            r"pic_\1",
            *extra,
        ]

    def test_no_matches_prints_message_and_exits_zero(self) -> None:
        code, out, _ = _run_cli(["--dir", ".", "--match", "zzz"])
        self.assertEqual(code, 0)
        self.assertIn("No files matched the renaming criteria", out)

    def test_preview_without_apply_is_dry_run(self) -> None:
        self._seed_photos()
        code, out, _ = _run_cli(self._rename_args("--dry-run"))
        self.assertEqual(code, 0)
        self.assertIn("=== Rename Preview (2 files to rename) ===", out)
        self.assertIn("photo1.jpg  ==>  pic_1.jpg", out)
        self.assertIn("[DRY RUN] No files were renamed.", out)
        self.assertTrue(Path("photo1.jpg").exists())

    def test_collision_detected_via_cli_blocks_execution(self) -> None:
        Path("dup1.txt").write_text("a")
        Path("dup2.txt").write_text("b")
        code, _, err = _run_cli(
            ["--dir", ".", "--match", r"dup\d", "--replace", "same"]
        )
        self.assertEqual(code, 1)
        self.assertIn("ERROR: Collisions detected!", err)
        self.assertIn("Duplicate target 'same.txt'", err)

    @patch("builtins.input", return_value="n")
    def test_declined_confirmation_cancels_rename(self, mock_input: MagicMock) -> None:
        self._seed_photos()
        code, out, _ = _run_cli(self._rename_args("--apply"))
        self.assertEqual(code, 0)
        self.assertIn("Renaming cancelled.", out)
        mock_input.assert_called_once()
        self.assertTrue(Path("photo1.jpg").exists())

    def test_apply_with_yes_renames_and_writes_manifest(self) -> None:
        self._seed_photos()
        custom_manifest = "my_manifest.json"
        code, out, _ = _run_cli(
            self._rename_args("--apply", "--yes", "--manifest", custom_manifest)
        )
        self.assertEqual(code, 0)
        self.assertIn("Successfully renamed 2 file(s).", out)
        self.assertIn(f"Undo manifest saved to '{custom_manifest}'.", out)
        self.assertTrue(Path("pic_1.jpg").exists())
        self.assertTrue(Path(custom_manifest).exists())

    def test_undo_restores_previous_names_from_manifest(self) -> None:
        self._seed_photos()
        _run_cli(self._rename_args("--apply", "--yes"))
        self.assertFalse(Path("photo1.jpg").exists())

        code, out, _ = _run_cli(["--undo"])
        self.assertEqual(code, 0)
        self.assertIn("Undo completed! Rolled back 2 file(s).", out)
        self.assertIn("Restored:", out)
        self.assertTrue(Path("photo1.jpg").exists())
        self.assertTrue(Path("photo2.jpg").exists())

    def test_undo_without_manifest_fails_gracefully(self) -> None:
        code, out, err = _run_cli(["--undo", "--manifest", "absent_manifest.json"])
        self.assertEqual(code, 1)
        self.assertIn("Error during undo:", err)


if __name__ == "__main__":
    unittest.main()
