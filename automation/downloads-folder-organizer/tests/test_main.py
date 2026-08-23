import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, List, Tuple
from unittest.mock import MagicMock, patch

from main import (
    build_organize_plan,
    categorize_file,
    execute_organize_plan,
    load_category_rules,
    main,
    resolve_collision,
    rollback_organize,
)


class TestDownloadsFolderOrganizer(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.rules = load_category_rules()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_categorize_file(self):
        self.assertEqual(categorize_file(Path("document.pdf"), self.rules), "Documents")
        self.assertEqual(categorize_file(Path("photo.jpg"), self.rules), "Images")
        self.assertEqual(categorize_file(Path("script.py"), self.rules), "Code")
        self.assertEqual(categorize_file(Path("archive.zip"), self.rules), "Archives")
        self.assertEqual(categorize_file(Path("unknown.xyz123"), self.rules), "Others")

    def test_custom_rules(self):
        config_path = self.test_dir / "custom_rules.json"
        config_data = {"Ebooks": [".epub", ".mobi"], "Cad": [".dwg"]}
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f)

        custom_rules = load_category_rules(config_path)
        self.assertIn("Ebooks", custom_rules)
        self.assertEqual(categorize_file(Path("book.epub"), custom_rules), "Ebooks")

    def test_resolve_collision(self):
        f1 = self.test_dir / "test.txt"
        f1.touch()

        collided = resolve_collision(f1)
        self.assertEqual(collided.name, "test_1.txt")

    def test_build_organize_plan_and_execute(self):
        f_pdf = self.test_dir / "report.pdf"
        f_img = self.test_dir / "avatar.png"
        f_pdf.write_text("pdf data")
        f_img.write_text("png data")

        plan = build_organize_plan(self.test_dir, self.rules)
        self.assertEqual(len(plan), 2)

        manifest_path = self.test_dir / "manifest.json"
        executed = execute_organize_plan(plan, manifest_path=manifest_path)

        self.assertEqual(len(executed), 2)
        self.assertTrue((self.test_dir / "Documents" / "report.pdf").exists())
        self.assertTrue((self.test_dir / "Images" / "avatar.png").exists())
        self.assertFalse(f_pdf.exists())

        # Test Rollback
        restored = rollback_organize(manifest_path)
        self.assertEqual(len(restored), 2)
        self.assertTrue(f_pdf.exists())
        self.assertTrue(f_img.exists())

    def test_date_subfolder_sorting(self):
        f_doc = self.test_dir / "notes.txt"
        f_doc.write_text("some notes")

        plan = build_organize_plan(
            self.test_dir, self.rules, by_date=True, date_format="%Y-%m"
        )
        self.assertEqual(len(plan), 1)
        target_path_str = str(plan[0].target)
        self.assertIn("Documents", target_path_str)


class TestOrganizerRulesAndPlanning(unittest.TestCase):
    """Rule loading, MIME fallback and plan construction details."""

    def setUp(self) -> None:
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir)

    def test_missing_custom_rules_file_raises(self) -> None:
        """A nonexistent custom rules path raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            load_category_rules(self.test_dir / "ghost.json")

    def test_custom_rules_normalize_extensions(self) -> None:
        """Extensions without dots and uppercase forms are normalized."""
        config_path = self.test_dir / "rules.json"
        config_path.write_text(json.dumps({"Models": ["OBJ", "stl"]}), encoding="utf-8")
        rules = load_category_rules(config_path)
        self.assertEqual(rules["Models"], [".obj", ".stl"])

    def test_mime_fallback_audio(self) -> None:
        """Unknown extensions fall back to MIME-based categories."""
        rules = {"Audio": [".mp3"], "Documents": [".txt"]}
        self.assertEqual(categorize_file(Path("song.mid"), rules), "Audio")

    def test_mime_category_missing_from_rules_is_others(self) -> None:
        """MIME hits whose category is absent from rules yield Others."""
        rules = {"Docs": [".pdf"]}
        self.assertEqual(categorize_file(Path("movie.mp4"), rules), "Others")

    def test_resolve_collision_increments_until_free(self) -> None:
        """Colliding names append _1, _2, ... until a free slot is found."""
        (self.test_dir / "file.txt").touch()
        (self.test_dir / "file_1.txt").touch()
        resolved = resolve_collision(self.test_dir / "file.txt")
        self.assertEqual(resolved.name, "file_2.txt")

    def test_plan_skips_directories_and_invalid_root(self) -> None:
        """Only top-level files are planned; bad roots raise ValueError."""
        sub = self.test_dir / "Images"
        sub.mkdir()
        (sub / "nested.png").write_text("x")
        (self.test_dir / "top.jpg").write_text("x")

        plan = build_organize_plan(self.test_dir, load_category_rules())
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0].source.name, "top.jpg")

        with self.assertRaises(ValueError):
            build_organize_plan(self.test_dir / "nope", {})

    def test_by_date_oserror_keeps_plain_target(self) -> None:
        """A stat failure during date sorting keeps the plain category dir."""
        (self.test_dir / "report.pdf").write_text("data")
        broken_datetime = MagicMock()
        broken_datetime.datetime.fromtimestamp.side_effect = OSError
        with patch("main.datetime", broken_datetime):
            plan = build_organize_plan(
                self.test_dir,
                load_category_rules(),
                by_date=True,
                date_format="%Y-%m",
            )
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0].target.parent.name, "Documents")


class TestExecuteAndRollback(unittest.TestCase):
    """Move execution, failure tolerance and manifest handling."""

    def setUp(self) -> None:
        self.test_dir = Path(tempfile.mkdtemp())
        self.manifest = self.test_dir / "undo.json"

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir)

    def _plan_for(self, name: str) -> Any:
        """Build a one-item plan for a named source file."""
        source = self.test_dir / name
        source.write_text("payload")
        target_dir = self.test_dir / "Documents"
        return (
            build_organize_plan(self.test_dir, load_category_rules()),
            source,
            target_dir,
        )

    def test_failed_move_reported_and_excluded(self) -> None:
        """Unmovable sources print an error and miss the executed list."""
        plan_items, source, _target_dir = self._plan_for("doc.pdf")
        ghost_item = plan_items[0]
        source.unlink()  # make the planned move fail

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            executed = execute_organize_plan([ghost_item])

        self.assertEqual(executed, [])
        self.assertIn("Failed to move", stderr.getvalue())

    def test_manifest_not_written_when_nothing_executed(self) -> None:
        """No executed moves means no manifest file is created."""
        plan_items, source, _target_dir = self._plan_for("doc.pdf")
        source.unlink()

        with redirect_stderr(io.StringIO()):
            execute_organize_plan(plan_items, manifest_path=self.manifest)

        self.assertFalse(self.manifest.exists())

    def test_rollback_missing_manifest_raises(self) -> None:
        """Undo without a manifest raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            rollback_organize(self.manifest)

    def test_rollback_skips_disappeared_targets(self) -> None:
        """Targets already gone are skipped during rollback."""
        source = self.test_dir / "note.txt"
        source.write_text("data")
        target = self.test_dir / "Documents" / "note.txt"
        target.parent.mkdir()
        moved: List[Tuple[str, str]] = [(str(source), str(target))]
        self.manifest.write_text(
            json.dumps({"moves": [{"source": s, "target": t} for s, t in moved]}),
            encoding="utf-8",
        )
        # Target vanished before rollback.
        restored = rollback_organize(self.manifest)
        self.assertEqual(restored, [])

    def test_rollback_restores_files(self) -> None:
        """Rollback moves targets back to their recorded sources."""
        source = self.test_dir / "note.txt"
        source.write_text("data")
        target = self.test_dir / "Documents" / "note.txt"
        target.parent.mkdir()
        shutil.move(str(source), str(target))
        self.manifest.write_text(
            json.dumps(
                {"moves": [{"source": str(source.resolve()), "target": str(target)}]}
            ),
            encoding="utf-8",
        )

        restored = rollback_organize(self.manifest)
        self.assertEqual(len(restored), 1)
        self.assertTrue(source.exists())
        self.assertFalse(target.exists())


class TestOrganizerCli(unittest.TestCase):
    """CLI-level tests covering main() flows via sys.argv."""

    def setUp(self) -> None:
        self.test_dir = Path(tempfile.mkdtemp())
        self.manifest = self.test_dir / "undo.json"

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir)

    def _run_cli(self, *args: str, stdin_text: str = "") -> Any:
        """Run main() with argv/stdin patched, capturing streams and code."""
        stdout, stderr = io.StringIO(), io.StringIO()
        argv = ["main.py"] + list(args)
        exit_code = None
        with redirect_stdout(stdout), redirect_stderr(stderr), patch(
            "sys.argv", argv
        ), patch("builtins.input", return_value=stdin_text or "n"):
            try:
                main()
            except SystemExit as exc:
                exit_code = exc.code
        return stdout.getvalue(), stderr.getvalue(), exit_code

    def test_dry_run_previews_without_moving(self) -> None:
        """Dry-run prints the plan and leaves files in place."""
        (self.test_dir / "photo.png").write_text("img")
        stdout, _, code = self._run_cli("-d", str(self.test_dir), "--dry-run")

        self.assertIsNone(code)
        self.assertIn("[DRY RUN]", stdout)
        self.assertIn("photo.png ==> Images", stdout.replace("\\", "/"))
        self.assertTrue((self.test_dir / "photo.png").exists())

    def test_no_loose_files_message(self) -> None:
        """Empty directories short-circuit with a friendly message."""
        stdout, _, _ = self._run_cli("-d", str(self.test_dir))
        self.assertIn("No loose files found", stdout)

    def test_apply_with_yes_moves_files(self) -> None:
        """--apply --yes executes moves and writes the manifest."""
        (self.test_dir / "archive.zip").write_text("zip")
        stdout, _, _ = self._run_cli(
            "-d",
            str(self.test_dir),
            "--apply",
            "--yes",
            "--manifest",
            str(self.manifest),
        )

        self.assertIn("Successfully organized 1 file(s)", stdout)
        self.assertTrue((self.test_dir / "Archives" / "archive.zip").exists())
        self.assertTrue(self.manifest.exists())

    def test_apply_cancelled_at_prompt(self) -> None:
        """Answering 'n' at the prompt cancels all moves."""
        (self.test_dir / "clip.mp4").write_text("vid")
        stdout, _, _ = self._run_cli(
            "-d",
            str(self.test_dir),
            "--apply",
            "--manifest",
            str(self.manifest),
            stdin_text="n",
        )

        self.assertIn("Operation cancelled", stdout)
        self.assertTrue((self.test_dir / "clip.mp4").exists())
        self.assertFalse(self.manifest.exists())

    def test_apply_confirmed_via_prompt(self) -> None:
        """Answering 'y' at the prompt executes the moves."""
        (self.test_dir / "tune.mp3").write_text("audio")
        stdout, _, _ = self._run_cli(
            "-d",
            str(self.test_dir),
            "--apply",
            "--manifest",
            str(self.manifest),
            stdin_text="y",
        )

        self.assertIn("Successfully organized 1 file(s)", stdout)
        self.assertTrue((self.test_dir / "Audio" / "tune.mp3").exists())

    def test_undo_flow_restores_files(self) -> None:
        """--undo rolls back a prior organization run."""
        (self.test_dir / "sheet.csv").write_text("csv")
        self._run_cli(
            "-d",
            str(self.test_dir),
            "--apply",
            "--yes",
            "--manifest",
            str(self.manifest),
        )
        self.assertTrue((self.test_dir / "Documents" / "sheet.csv").exists())

        stdout, _, _ = self._run_cli("--undo", "--manifest", str(self.manifest))
        self.assertIn("Restored 1 file(s)", stdout)
        self.assertTrue((self.test_dir / "sheet.csv").exists())
        self.assertFalse((self.test_dir / "Documents" / "sheet.csv").exists())

    def test_undo_error_returns_exit_code_one(self) -> None:
        """A failing undo reports the error and exits 1."""
        _, stderr, code = self._run_cli(
            "--undo", "--manifest", str(self.test_dir / "ghost.json")
        )
        self.assertEqual(code, 1)
        self.assertIn("Error during undo", stderr)

    def test_config_error_aborts_with_exit_code_one(self) -> None:
        """An unreadable custom rules file exits 1 with a clear message."""
        bad_config = self.test_dir / "bad.json"
        bad_config.write_text("{oops", encoding="utf-8")

        _, stderr, code = self._run_cli("-d", str(self.test_dir), "-c", str(bad_config))
        self.assertEqual(code, 1)
        self.assertIn("Error loading category rules", stderr)

    def test_missing_config_file_aborts_with_exit_code_one(self) -> None:
        """A nonexistent custom rules file exits 1 cleanly as well."""
        _, stderr, code = self._run_cli(
            "-d", str(self.test_dir), "-c", str(self.test_dir / "ghost.json")
        )
        self.assertEqual(code, 1)
        self.assertIn("Error loading category rules", stderr)

    def test_preview_lists_categories(self) -> None:
        """The preview header counts every proposed move."""
        (self.test_dir / "a.pdf").write_text("a")
        (self.test_dir / "b.jpg").write_text("b")
        stdout, _, _ = self._run_cli("-d", str(self.test_dir))

        self.assertIn("Organization Preview (2 files to move)", stdout)
        self.assertIn("[Documents] a.pdf", stdout)


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
