"""Unit tests for intent-expiry main.py."""

import contextlib
import io
import subprocess  # nosec B404
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from main import IntentAuditor, TodoItem, main, parse_args


class TestIntentExpiry(unittest.TestCase):
    """End-to-end audit behaviour without git access."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_audit_todo_completed(self):
        """A TODO whose referenced symbol exists is marked COMPLETED."""
        code_file = self.repo_dir / "app.py"
        code_file.write_text(
            "# TODO: implement process_data\ndef process_data():\n    pass\n",
            encoding="utf-8",
        )

        auditor = IntentAuditor(self.repo_dir, use_git=False)
        items = auditor.audit()

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].tag, "TODO")
        self.assertEqual(items[0].status, "COMPLETED")

    def test_audit_todo_active(self):
        """Prose-only TODO comments remain ACTIVE."""
        code_file = self.repo_dir / "app.py"
        code_file.write_text(
            "# TODO: refactor database queries later\n",
            encoding="utf-8",
        )

        auditor = IntentAuditor(self.repo_dir, use_git=False)
        items = auditor.audit()

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].status, "ACTIVE")


class TestSymbolIndexing(unittest.TestCase):
    """Tests for repository symbol indexing."""

    def setUp(self) -> None:
        """Create a fresh temporary repo root per test."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        """Remove the temporary repo root."""
        self.temp_dir.cleanup()

    def test_index_collects_defs_and_classes_across_languages(self) -> None:
        """def/class definitions are collected from supported source files."""
        (self.repo_dir / "service.py").write_text(
            "class OrderService:\n\n"
            "    def ship_order(self):\n"
            "        return True\n",
            encoding="utf-8",
        )
        src = self.repo_dir / "src"
        src.mkdir()
        (src / "widget.ts").write_text("class WidgetCache {}\n", encoding="utf-8")
        (self.repo_dir / "notes.txt").write_text(
            "def not_code_at_all():\n", encoding="utf-8"
        )

        auditor = IntentAuditor(self.repo_dir)
        auditor.index_repo_symbols()

        self.assertIn("OrderService", auditor.all_symbols)
        self.assertIn("ship_order", auditor.all_symbols)
        self.assertIn("WidgetCache", auditor.all_symbols)
        self.assertNotIn("not_code_at_all", auditor.all_symbols)

    def test_index_survives_unreadable_files(self) -> None:
        """Unreadable source files are skipped instead of crashing indexing."""

        def raise_oserror(self: Path, *args: object, **kwargs: object) -> str:
            """Simulate an I/O failure on every text read."""
            raise OSError("locked")

        (self.repo_dir / "svc.py").write_text("def boot():\n", encoding="utf-8")
        auditor = IntentAuditor(self.repo_dir)
        with mock.patch.object(Path, "read_text", raise_oserror):
            auditor.index_repo_symbols()
        self.assertEqual(auditor.all_symbols, set())


class TestGitBlame(unittest.TestCase):
    """Tests for git blame lookups (subprocess fully mocked)."""

    def setUp(self) -> None:
        """Create a fresh temporary repo root per test."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        """Remove the temporary repo root."""
        self.temp_dir.cleanup()

    @staticmethod
    def _fake_completed_process(stdout: str) -> mock.Mock:
        """Build a fake CompletedProcess-like object."""
        proc = mock.Mock()
        proc.stdout = stdout
        return proc

    def test_blame_parses_porcelain_output(self) -> None:
        """Author, epoch timestamp and commit hash come from porcelain blame."""
        porcelain = (
            "9f2c1ab77e44aa01 3 3 1\n"
            "author Grace Hopper\n"
            "author-time 1700000000\n"
            "author-tz -0500\n"
            "committer Dev\n"
            "summary fix bug\n"
            "\n"
            "        # TODO: cleanup\n"
        )
        auditor = IntentAuditor(self.repo_dir, use_git=True)
        with mock.patch(
            "subprocess.run",
            return_value=self._fake_completed_process(porcelain),
        ) as fake_run:
            author, date, commit = auditor.get_git_blame_info("app.py", 7)
        self.assertEqual(author, "Grace Hopper")
        self.assertEqual(date, "1700000000")
        self.assertEqual(commit, "9f2c1ab77e44aa01")
        self.assertEqual(fake_run.call_args.kwargs["cwd"], str(self.repo_dir))

    def test_blame_subprocess_error_returns_unknowns(self) -> None:
        """A failing git blame degrades to Unknown metadata."""
        auditor = IntentAuditor(self.repo_dir, use_git=True)
        with mock.patch(
            "subprocess.run",
            side_effect=subprocess.SubprocessError("blame failed"),
        ):
            result = auditor.get_git_blame_info("app.py", 1)
        self.assertEqual(result, ("Unknown", "Unknown", "Unknown"))

    def test_blame_missing_git_binary_returns_unknowns(self) -> None:
        """A missing git executable also yields Unknown metadata."""
        auditor = IntentAuditor(self.repo_dir, use_git=True)
        with mock.patch("subprocess.run", side_effect=OSError("no git")):
            result = auditor.get_git_blame_info("app.py", 1)
        self.assertEqual(result, ("Unknown", "Unknown", "Unknown"))

    def test_blame_disabled_returns_unknowns_without_subprocess(self) -> None:
        """use_git=False short-circuits before any git invocation."""
        auditor = IntentAuditor(self.repo_dir, use_git=False)
        with mock.patch("subprocess.run") as fake_run:
            result = auditor.get_git_blame_info("app.py", 1)
        fake_run.assert_not_called()
        self.assertEqual(result, ("Unknown", "Unknown", "Unknown"))

    def test_audit_attaches_unknown_metadata_when_git_disabled(self) -> None:
        """Audit items carry Unknown author/date/commit when git is disabled."""
        (self.repo_dir / "app.py").write_text(
            "# FIXME: tighten input validation\n", encoding="utf-8"
        )
        items = IntentAuditor(self.repo_dir, use_git=False).audit()
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.author, "Unknown")
        self.assertEqual(item.date, "Unknown")
        self.assertEqual(item.commit, "Unknown")
        self.assertEqual(item.file_path, "app.py")
        self.assertEqual(item.line_number, 1)


class TestFileSkipping(unittest.TestCase):
    """Tests for which files the audit walks and reads."""

    def setUp(self) -> None:
        """Create a fresh temporary repo root per test."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        """Remove the temporary repo root."""
        self.temp_dir.cleanup()

    def test_dotfiles_and_binary_extensions_are_skipped(self) -> None:
        """Hidden dotfiles and binary artefacts never surface TODO items."""
        (self.repo_dir / ".hidden.cfg").write_text(
            "# TODO: rotate key soon\n", encoding="utf-8"
        )
        (self.repo_dir / "bundle.pyc").write_text(
            "# TODO: rebuild bytecode\n", encoding="utf-8"
        )
        (self.repo_dir / "logo.png").write_text(
            "# TODO: recompress\n", encoding="utf-8"
        )
        (self.repo_dir / "archive.zip").write_text(
            "# TODO: prune archive\n", encoding="utf-8"
        )
        (self.repo_dir / "photo.jpg").write_text("# TODO: resize\n", encoding="utf-8")
        (self.repo_dir / "real.py").write_text(
            "# TODO: real work item later\n", encoding="utf-8"
        )

        items = IntentAuditor(self.repo_dir, use_git=False).audit()

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].file_path, "real.py")

    def test_unreadable_file_is_skipped(self) -> None:
        """Files that cannot be read during audit are silently ignored."""

        def raise_oserror(self: Path, *args: object, **kwargs: object) -> str:
            """Simulate an I/O failure on every text read."""
            raise OSError("disk error")

        (self.repo_dir / "broken.py").write_text("# TODO: x\n", encoding="utf-8")
        with mock.patch.object(Path, "read_text", raise_oserror):
            items = IntentAuditor(self.repo_dir, use_git=False).audit()
        self.assertEqual(items, [])


class TestClassification(unittest.TestCase):
    """Tests for ACTIVE / COMPLETED / OBSOLETE classification rules."""

    def setUp(self) -> None:
        """Create a fresh temporary repo root per test."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        """Remove the temporary repo root."""
        self.temp_dir.cleanup()

    def _audit_single_comment(self, text: str) -> TodoItem:
        """Write one tagged comment into an empty repo and return its item."""
        (self.repo_dir / "only.py").write_text(f"# {text}\n", encoding="utf-8")
        items = IntentAuditor(self.repo_dir, use_git=False).audit()
        assert items, f"expected one item for comment: {text}"
        return items[0]

    def test_completion_keyword_marks_item_completed(self) -> None:
        """Comments containing done/fixed/implemented are COMPLETED."""
        item = self._audit_single_comment("FIXME: this was fixed last sprint")
        self.assertEqual(item.status, "COMPLETED")
        self.assertIn("done/fixed", item.reason)

    def test_lowercase_tag_is_normalized_to_uppercase(self) -> None:
        """Tag matching is case-insensitive but reported uppercase."""
        item = self._audit_single_comment("todo: tidy the module docstring")
        self.assertEqual(item.tag, "TODO")
        self.assertEqual(item.status, "ACTIVE")

    def test_missing_symbol_marks_item_obsolete(self) -> None:
        """Code-style identifiers absent from the codebase mean OBSOLETE."""
        item = self._audit_single_comment(
            "HACK: remove once legacy_retry_helper is gone"
        )
        self.assertEqual(item.status, "OBSOLETE")
        self.assertIn("no longer exist", item.reason)

    def test_existing_symbol_marks_item_completed(self) -> None:
        """CamelCase identifiers present in the codebase mean COMPLETED."""
        (self.repo_dir / "svc.py").write_text(
            "class CacheWarmer:\n    pass\n", encoding="utf-8"
        )
        item = self._audit_single_comment("TODO: delete CacheWarmer shim")
        self.assertEqual(item.status, "COMPLETED")
        self.assertIn("now exist", item.reason)

    def test_prose_words_do_not_trigger_symbol_logic(self) -> None:
        """Plain lowercase prose stays ACTIVE instead of being flagged."""
        item = self._audit_single_comment("TODO: rewrite the retry logic docs")
        self.assertEqual(item.status, "ACTIVE")
        self.assertEqual(item.reason, "Pending implementation.")

    def test_short_or_stopword_tokens_ignored(self) -> None:
        """Tiny tokens and stop words never count as symbol references."""
        auditor = IntentAuditor(self.repo_dir, use_git=False)
        item = TodoItem(
            file_path="a.py",
            line_number=1,
            tag="TODO",
            comment_text="USE the FOR loop AND THE api map",
            referenced_symbols=["USE", "FOR", "AND", "THE", "api"],
        )
        auditor.classify_item(item)
        self.assertEqual(item.status, "ACTIVE")


class TestParseArgs(unittest.TestCase):
    """Tests for CLI argument parsing."""

    def test_path_is_required(self) -> None:
        """--path is mandatory and lands on the namespace."""
        args = parse_args(["--path", "/some/repo"])
        self.assertEqual(args.path, "/some/repo")
        self.assertFalse(args.no_git)

    def test_no_git_flag_enables_disable(self) -> None:
        """--no-git flips the git toggle on the namespace."""
        args = parse_args(["--path", "/some/repo", "--no-git"])
        self.assertTrue(args.no_git)

    def test_missing_path_exits_via_argparse(self) -> None:
        """Omitting the required --path raises SystemExit."""
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parse_args([])


class TestMainEntrypoint(unittest.TestCase):
    """End-to-end tests for the command-line entrypoint."""

    def setUp(self) -> None:
        """Create a small audited tree used by the CLI tests."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name)
        (self.repo_dir / "app.py").write_text(
            "# TODO: rewrite retry logic docs\n"
            "# HACK: drop once legacy_retry_helper is gone\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        """Remove the temporary tree."""
        self.temp_dir.cleanup()

    def test_main_prints_report_and_returns_zero(self) -> None:
        """main() prints the audit report listing each classified item."""
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["--path", str(self.repo_dir), "--no-git"])
        out = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("=== Intent Expiry Audit Report ===", out)
        self.assertIn("Total Comments Found: 2", out)
        self.assertIn("[ACTIVE] TODO at app.py:1", out)
        self.assertIn("[OBSOLETE] HACK at app.py:2", out)
        self.assertIn("Comment:", out)
        self.assertIn("Reason:", out)

    def test_script_main_guard_runs_cli(self) -> None:
        """Running the script file end-to-end audits a tree and exits 0."""
        script = Path(__file__).resolve().parent.parent / "main.py"
        proc = subprocess.run(  # nosec B603
            [sys.executable, str(script), "--path", str(self.repo_dir), "--no-git"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Intent Expiry Audit Report", proc.stdout)


if __name__ == "__main__":
    unittest.main()
