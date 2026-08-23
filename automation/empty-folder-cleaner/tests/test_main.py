import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import patch

from main import (
    CleaningCandidate,
    execute_cleaning,
    find_empty_folders,
    is_folder_excluded,
    is_hidden_or_system,
    main,
)


class TestEmptyFolderCleaner(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_is_hidden_or_system(self):
        self.assertTrue(is_hidden_or_system(Path(".DS_Store")))
        self.assertTrue(is_hidden_or_system(Path(".hidden_folder")))
        self.assertTrue(is_hidden_or_system(Path("desktop.ini")))
        self.assertFalse(is_hidden_or_system(Path("regular_file.txt")))

    def test_is_folder_excluded(self):
        self.assertTrue(is_folder_excluded(Path(".git"), {".git"}))
        self.assertTrue(is_folder_excluded(Path("node_modules"), {"node_modules"}))
        self.assertFalse(is_folder_excluded(Path("my_folder"), {".git"}))

    def test_find_empty_folders_nested(self):
        # Create nested empty tree: level1/level2/level3
        nested = self.test_dir / "level1" / "level2" / "level3"
        nested.mkdir(parents=True, exist_ok=True)

        # Non-empty branch: non_empty/file.txt
        non_empty = self.test_dir / "non_empty"
        non_empty.mkdir(parents=True, exist_ok=True)
        (non_empty / "file.txt").write_text("data")

        candidates = find_empty_folders(self.test_dir)
        candidate_dirs = [c.directory for c in candidates]

        self.assertIn(self.test_dir / "level1" / "level2" / "level3", candidate_dirs)
        self.assertIn(self.test_dir / "level1" / "level2", candidate_dirs)
        self.assertIn(self.test_dir / "level1", candidate_dirs)
        self.assertNotIn(non_empty, candidate_dirs)

    def test_execute_cleaning(self):
        empty_sub = self.test_dir / "empty_sub"
        empty_sub.mkdir()

        junk_sub = self.test_dir / "junk_sub"
        junk_sub.mkdir()
        (junk_sub / ".DS_Store").touch()

        candidates = find_empty_folders(
            self.test_dir, ignore_hidden_files=True, delete_junk_files=True
        )
        folders_del, files_del = execute_cleaning(candidates, dry_run=False)

        self.assertEqual(folders_del, 2)
        self.assertEqual(files_del, 1)
        self.assertFalse(empty_sub.exists())
        self.assertFalse(junk_sub.exists())

    def test_excluded_folders_ignored(self):
        git_dir = self.test_dir / ".git"
        git_dir.mkdir()

        candidates = find_empty_folders(self.test_dir, exclude_patterns={".git"})
        candidate_dirs = [c.directory for c in candidates]
        self.assertNotIn(git_dir, candidate_dirs)


class TestFindEmptyFoldersRules(unittest.TestCase):
    """Traversal and filtering rules of find_empty_folders."""

    def setUp(self) -> None:
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir)

    def test_invalid_root_raises_value_error(self) -> None:
        """A nonexistent root directory raises ValueError."""
        with self.assertRaises(ValueError):
            find_empty_folders(self.test_dir / "ghost")

    def test_parent_of_active_subtree_not_candidate(self) -> None:
        """Parents containing live subdirectories are never candidates."""
        parent = self.test_dir / "parent"
        sub = parent / "sub"
        sub.mkdir(parents=True)
        (sub / "keep.txt").write_text("data")

        candidates = find_empty_folders(self.test_dir)
        dirs = [c.directory for c in candidates]
        self.assertNotIn(parent, dirs)
        self.assertNotIn(sub, dirs)
        self.assertEqual(candidates, [])

    def test_keep_hidden_files_excludes_junk_only_folders(self) -> None:
        """ignore_hidden_files=False treats .DS_Store as real content."""
        junk_dir = self.test_dir / "junk_only"
        junk_dir.mkdir()
        (junk_dir / ".DS_Store").touch()

        candidates = find_empty_folders(self.test_dir, ignore_hidden_files=False)
        self.assertEqual([c.directory for c in candidates], [])

    def test_delete_junk_false_skips_junk_folders(self) -> None:
        """Junk-only folders stay when delete_junk_files is False."""
        junk_dir = self.test_dir / "junk_only"
        junk_dir.mkdir()
        (junk_dir / "desktop.ini").touch()

        candidates = find_empty_folders(self.test_dir, delete_junk_files=False)
        self.assertEqual([c.directory for c in candidates], [])


class TestExecuteCleaning(unittest.TestCase):
    """Deletion accounting and failure handling of execute_cleaning."""

    def setUp(self) -> None:
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir)

    def test_dry_run_counts_without_deleting(self) -> None:
        """dry_run=True reports counts but touches nothing on disk."""
        target = self.test_dir / "empty_sub"
        target.mkdir()
        candidates = [
            CleaningCandidate(directory=target, junk_files=[target / ".DS_Store"])
        ]

        folders_deleted, files_deleted = execute_cleaning(candidates, dry_run=True)

        self.assertEqual((folders_deleted, files_deleted), (1, 1))
        self.assertTrue(target.exists())

    def test_removal_failures_reported_with_zero_counts(self) -> None:
        """unlink/rmdir failures print errors and count nothing."""
        target = self.test_dir / "stuck"
        target.mkdir()
        candidate = CleaningCandidate(
            directory=target, junk_files=[target / ".DS_Store"]
        )
        (target / ".DS_Store").touch()

        stderr = io.StringIO()
        with redirect_stderr(stderr), patch.object(
            Path, "unlink", side_effect=OSError("locked")
        ), patch.object(Path, "rmdir", side_effect=OSError("busy")):
            folders_deleted, files_deleted = execute_cleaning(
                [candidate], dry_run=False
            )

        self.assertEqual((folders_deleted, files_deleted), (0, 0))
        output = stderr.getvalue()
        self.assertIn("Failed to remove file", output)
        self.assertIn("Failed to remove directory", output)


class TestEmptyFolderCleanerCli(unittest.TestCase):
    """CLI-level tests covering main() flows via sys.argv."""

    def setUp(self) -> None:
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir)

    def _run_cli(self, *args: str, stdin_text: str = "") -> Any:
        """Run main() with argv/stdin patched; capture streams and code."""
        stdout, stderr = io.StringIO(), io.StringIO()
        exit_code = None
        argv = ["main.py"] + list(args)
        with redirect_stdout(stdout), redirect_stderr(stderr), patch(
            "sys.argv", argv
        ), patch("builtins.input", return_value=stdin_text or "n"):
            try:
                main()
            except SystemExit as exc:
                exit_code = exc.code
        return stdout.getvalue(), stderr.getvalue(), exit_code

    def test_dry_run_lists_candidates_without_deleting(self) -> None:
        """Default (no --apply) behaviour is a non-destructive preview."""
        empty = self.test_dir / "empty_a"
        empty.mkdir()
        stdout, _, code = self._run_cli("-d", str(self.test_dir))

        self.assertIsNone(code)
        self.assertIn("[EMPTY]", stdout)
        self.assertIn("[DRY RUN]", stdout)
        self.assertTrue(empty.exists())

    def test_no_candidates_message(self) -> None:
        """Trees without empties report that nothing was found."""
        filled = self.test_dir / "filled"
        filled.mkdir()
        (filled / "x.txt").write_text("x")
        stdout, _, _ = self._run_cli("-d", str(self.test_dir))
        self.assertIn("No empty directories found.", stdout)

    def test_apply_yes_deletes_and_summarizes(self) -> None:
        """--apply --yes removes the tree and prints a summary."""
        nested = self.test_dir / "lvl1" / "lvl2"
        nested.mkdir(parents=True)

        stdout, _, _ = self._run_cli("-d", str(self.test_dir), "--apply", "--yes")

        self.assertIn("deleted 2 empty folder(s)", stdout)
        self.assertFalse((self.test_dir / "lvl1").exists())

    def test_apply_cancelled_at_prompt(self) -> None:
        """Answering 'n' at the confirmation prompt aborts deletion."""
        empty = self.test_dir / "empty_a"
        empty.mkdir()
        stdout, _, _ = self._run_cli(
            "-d", str(self.test_dir), "--apply", stdin_text="n"
        )

        self.assertIn("Operation cancelled", stdout)
        self.assertTrue(empty.exists())

    def test_apply_confirmed_via_prompt_deletes(self) -> None:
        """Answering 'y' at the prompt performs the deletion."""
        empty = self.test_dir / "empty_a"
        empty.mkdir()
        stdout, _, _ = self._run_cli(
            "-d", str(self.test_dir), "--apply", stdin_text="y"
        )

        self.assertIn("deleted 1 empty folder(s)", stdout)
        self.assertFalse(empty.exists())

    def test_keep_hidden_files_flag(self) -> None:
        """--keep-hidden-files protects junk-only directories."""
        junk = self.test_dir / "junk_only"
        junk.mkdir()
        (junk / "Thumbs.db").touch()
        stdout, _, _ = self._run_cli("-d", str(self.test_dir), "--keep-hidden-files")

        self.assertIn("No empty directories found.", stdout)
        self.assertTrue(junk.exists())

    def test_delete_junk_flag_purges_files(self) -> None:
        """--delete-junk --apply purges leftover system files."""
        junk = self.test_dir / "junk_only"
        junk.mkdir()
        (junk / ".DS_Store").touch()
        stdout, _, _ = self._run_cli(
            "-d",
            str(self.test_dir),
            "--delete-junk",
            "--apply",
            "--yes",
        )

        self.assertIn("Purged 1 leftover junk file(s).", stdout)
        self.assertFalse(junk.exists())

    def test_custom_exclude_patterns(self) -> None:
        """User-supplied exclude patterns are respected."""
        keep = self.test_dir / "precious"
        keep.mkdir()
        stdout, _, _ = self._run_cli(
            "-d",
            str(self.test_dir),
            "--exclude",
            "precious",
            "--apply",
            "--yes",
        )

        self.assertIn("No empty directories found.", stdout)
        self.assertTrue(keep.exists())


if __name__ == "__main__":
    unittest.main()
