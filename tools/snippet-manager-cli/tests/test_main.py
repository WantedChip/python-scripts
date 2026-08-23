"""Unit tests for Snippet Manager CLI."""

import contextlib
import io
import os
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Tuple
from unittest import mock

from main import SnippetManager, build_parser, format_snippet_display, main


class TestSnippetManager(unittest.TestCase):
    """Test suite for SnippetManager database logic and filters."""

    def setUp(self) -> None:
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.mgr = SnippetManager(db_path=self.temp_db.name)

    def tearDown(self) -> None:
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)

    def test_add_and_get_snippet(self) -> None:
        sid = self.mgr.add_snippet(
            title="Binary Search",
            language="python",
            code="def bsearch(): pass",
            tags="algorithm,search",
            description="Classic binary search",
        )
        self.assertGreater(sid, 0)
        snippet = self.mgr.get_snippet(str(sid))
        self.assertIsNotNone(snippet)
        self.assertEqual(snippet["title"], "Binary Search")
        self.assertEqual(snippet["language"], "python")

    def test_add_normalizes_case_of_language_and_tags(self) -> None:
        """Language and tag values are stored lowercased."""
        sid = self.mgr.add_snippet("Mixed", "PyThOn", "x=1", tags="ALGO,Search")
        snippet = self.mgr.get_snippet(str(sid))
        self.assertEqual(snippet["language"], "python")
        self.assertEqual(snippet["tags"], "algo,search")

    def test_list_with_language_filter(self) -> None:
        self.mgr.add_snippet("Py Quick", "python", "print('hi')")
        self.mgr.add_snippet("JS Quick", "javascript", "console.log('hi')")

        py_snippets = self.mgr.list_snippets(language="python")
        self.assertEqual(len(py_snippets), 1)
        self.assertEqual(py_snippets[0]["title"], "Py Quick")

    def test_list_with_tag_filter_and_newest_first_order(self) -> None:
        """Tag filters use substring matching and results sort by id DESC."""
        first = self.mgr.add_snippet("Old", "python", "a=1", tags="algo,sort")
        second = self.mgr.add_snippet("New", "python", "b=2", tags="sorting")
        tagged = self.mgr.list_snippets(tag="sort")
        self.assertEqual([s["id"] for s in tagged], [second, first])
        untagged = self.mgr.list_snippets(tag="nomatch-anywhere")
        self.assertEqual(untagged, [])

    def test_search_matches_code_description_and_tags(self) -> None:
        """Keyword search spans title, code, description, and tags."""
        self.mgr.add_snippet(
            "SQL Query", "sql", "SELECT * FROM users", tags="db,postgres"
        )
        self.mgr.add_snippet(
            "Other", "python", "pass", description="talks about postgres internals"
        )
        self.mgr.add_snippet("Unrelated", "rust", "fn main() {}")
        results = self.mgr.search_snippets("postgres")
        self.assertEqual(len(results), 2)

    def test_get_snippet_by_exact_title_is_case_insensitive(self) -> None:
        """Titles can be looked up without matching case."""
        self.mgr.add_snippet("CamelCase Title", "text", "body")
        found = self.mgr.get_snippet("camelcase TITLE")
        self.assertIsNotNone(found)
        self.assertEqual(found["title"], "CamelCase Title")

    def test_get_missing_snippet_returns_none(self) -> None:
        """Unknown IDs and titles yield None."""
        self.assertIsNone(self.mgr.get_snippet("9999"))
        self.assertIsNone(self.mgr.get_snippet("does-not-exist"))

    def test_delete_snippet(self) -> None:
        sid = self.mgr.add_snippet("To Delete", "text", "echo bye")
        self.assertTrue(self.mgr.delete_snippet(sid))
        self.assertIsNone(self.mgr.get_snippet(str(sid)))

    def test_delete_unknown_id_returns_false(self) -> None:
        """Deleting a non-existent snippet reports failure."""
        self.assertFalse(self.mgr.delete_snippet(424242))


class TestCopyToClipboard(unittest.TestCase):
    """Tests for the clipboard fallback chain."""

    def setUp(self) -> None:
        self.manager = SnippetManager(":memory:")

    def test_pyperclip_success(self) -> None:
        """A working pyperclip module handles the copy."""
        fake_pyperclip = mock.Mock()
        with mock.patch.dict(sys.modules, {"pyperclip": fake_pyperclip}):
            self.assertTrue(self.manager.copy_to_clipboard("payload"))
        fake_pyperclip.copy.assert_called_once_with("payload")

    def test_windows_fallback_uses_clip_utility(self) -> None:
        """Without pyperclip on Windows the clip utility is spawned."""
        proc = mock.Mock()
        with mock.patch.dict(sys.modules, {"pyperclip": None}):
            with mock.patch.object(sys, "platform", "win32"):
                with mock.patch("main.subprocess.Popen", return_value=proc) as popen:
                    result = self.manager.copy_to_clipboard("clip me")
        self.assertTrue(result)
        popen.assert_called_once()
        self.assertEqual(popen.call_args.args[0], ["clip"])
        proc.communicate.assert_called_once_with(input="clip me")

    def test_windows_failure_returns_false(self) -> None:
        """A failing clip subprocess is reported as unsuccessful."""
        with mock.patch.dict(sys.modules, {"pyperclip": None}):
            with mock.patch.object(sys, "platform", "win32"):
                with mock.patch(
                    "main.subprocess.Popen", side_effect=OSError("no clip")
                ):
                    self.assertFalse(self.manager.copy_to_clipboard("data"))

    def test_macos_fallback_uses_pbcopy(self) -> None:
        """Without pyperclip on macOS the pbcopy utility is spawned."""
        proc = mock.Mock()
        with mock.patch.dict(sys.modules, {"pyperclip": None}):
            with mock.patch.object(sys, "platform", "darwin"):
                with mock.patch("main.subprocess.Popen", return_value=proc) as popen:
                    result = self.manager.copy_to_clipboard("apple payload")
        self.assertTrue(result)
        self.assertEqual(popen.call_args.args[0], ["pbcopy"])

    def test_macos_failure_returns_false(self) -> None:
        """A failing pbcopy subprocess is reported as unsuccessful."""
        with mock.patch.dict(sys.modules, {"pyperclip": None}):
            with mock.patch.object(sys, "platform", "darwin"):
                with mock.patch(
                    "main.subprocess.Popen", side_effect=OSError("no pbcopy")
                ):
                    self.assertFalse(self.manager.copy_to_clipboard("data"))

    def test_unsupported_platform_returns_false(self) -> None:
        """Platforms without a native utility report failure."""
        with mock.patch.dict(sys.modules, {"pyperclip": None}):
            with mock.patch.object(sys, "platform", "linux"):
                self.assertFalse(self.manager.copy_to_clipboard("nothing"))


class TestFormatSnippetDisplay(unittest.TestCase):
    """Tests for console rendering of snippets."""

    @staticmethod
    def make_snippet(**overrides: Any) -> Dict[str, Any]:
        """Build a representative snippet dict with optional overrides."""
        snippet: Dict[str, Any] = {
            "id": 7,
            "title": "Hello",
            "language": "python",
            "code": "print('hello')\nprint('world')",
            "description": "",
            "tags": "",
            "created_at": "2026-07-24",
        }
        snippet.update(overrides)
        return snippet

    def test_format_display_includes_header_and_numbering(self) -> None:
        s = {
            "id": 1,
            "title": "Hello",
            "language": "python",
            "code": "print('hello')",
            "description": "Greeting",
            "tags": "test",
            "created_at": "2026-07-24",
        }
        display = format_snippet_display(s)
        self.assertIn("Snippet #1: Hello", display)
        self.assertIn("1 | print('hello')", display)

    def test_display_without_description_shows_none_tags(self) -> None:
        """Empty descriptions are omitted and empty tags render as None."""
        display = format_snippet_display(self.make_snippet())
        self.assertNotIn("Description:", display)
        self.assertIn("Tags: None", display)
        self.assertIn("2 | print('world')", display)


class TestParser(unittest.TestCase):
    """Tests for argparse subcommand definitions."""

    def test_add_subcommand_parses_all_fields(self) -> None:
        parsed = build_parser().parse_args(
            [
                "add",
                "My Snippet",
                "--lang",
                "python",
                "--code",
                "x=1",
                "--tags",
                "demo",
                "--description",
                "desc",
            ]
        )
        self.assertEqual(parsed.command, "add")
        self.assertEqual(parsed.title, "My Snippet")
        self.assertEqual(parsed.lang, "python")
        self.assertEqual(parsed.code, "x=1")
        self.assertEqual(parsed.tags, "demo")
        self.assertEqual(parsed.description, "desc")

    def test_query_subcommands_parse_expected_arguments(self) -> None:
        """list/search/show/copy/delete expose their documented arguments."""
        parser = build_parser()
        self.assertEqual(parser.parse_args(["list"]).command, "list")
        filtered = parser.parse_args(["list", "--lang", "py", "--tag", "util"])
        self.assertEqual(filtered.lang, "py")
        self.assertEqual(filtered.tag, "util")
        search = parser.parse_args(["search", "binary"])
        self.assertEqual(search.keyword, "binary")
        show = parser.parse_args(["show", "12"])
        self.assertEqual(show.id_or_title, "12")
        copy_cmd = parser.parse_args(["copy", "quick sort"])
        self.assertEqual(copy_cmd.id_or_title, "quick sort")
        delete = parser.parse_args(["delete", "3"])
        self.assertEqual(delete.id, 3)


class TestMainCli(unittest.TestCase):
    """End-to-end tests for the main() command dispatch."""

    def capture_main(self, args: List[str]) -> Tuple[int, str]:
        """Run main() capturing stdout; caller sets up the DB environment."""
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(args)
        return code, buffer.getvalue()

    def test_no_command_prints_help(self) -> None:
        """Invoking without a subcommand shows usage help."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with contextlib.chdir(tmp_dir):
                code, output = self.capture_main([])
        self.assertEqual(code, 0)
        self.assertIn("usage:", output)

    def test_add_then_list_round_trip(self) -> None:
        """Adding via the CLI persists a snippet that listing can find."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with contextlib.chdir(tmp_dir):
                code_add, out_add = self.capture_main(
                    [
                        "add",
                        "Round Trip",
                        "--lang",
                        "Python",
                        "--code",
                        "y=2",
                        "--tags",
                        "Demo",
                    ]
                )
                code_list, out_list = self.capture_main(["list"])
                self.assertEqual(code_add, 0)
                self.assertIn("Added snippet #1: 'Round Trip'", out_add)
                self.assertTrue(os.path.exists(os.path.join(tmp_dir, "snippets.db")))
        self.assertEqual(code_list, 0)
        self.assertIn("Found 1 snippets:", out_list)
        self.assertIn("[1] Round Trip (python)", out_list)

    def test_search_reports_matches(self) -> None:
        """The search subcommand prints matching rows."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with contextlib.chdir(tmp_dir):
                self.capture_main(
                    ["add", "Finder", "--lang", "sql", "--code", "SELECT 1"]
                )
                code, output = self.capture_main(["search", "select"])
        self.assertEqual(code, 0)
        self.assertIn("Search results for 'select':", output)
        self.assertIn("[1] Finder (sql)", output)

    def test_show_renders_existing_and_missing(self) -> None:
        """Show prints full details when found, else a not-found notice."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with contextlib.chdir(tmp_dir):
                self.capture_main(
                    ["add", "Visible", "--lang", "go", "--code", "fmt.Println(1)"]
                )
                _, found_output = self.capture_main(["show", "Visible"])
                _, missing_output = self.capture_main(["show", "ghost-title"])
        self.assertIn("=== Snippet #1: Visible ===", found_output)
        self.assertIn("Snippet not found.", missing_output)

    def test_copy_success_message(self) -> None:
        """Successful clipboard copies print a confirmation line."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with contextlib.chdir(tmp_dir):
                self.capture_main(
                    ["add", "Copied", "--lang", "sh", "--code", "echo hi"]
                )
                with mock.patch.object(
                    SnippetManager, "copy_to_clipboard", return_value=True
                ):
                    code, output = self.capture_main(["copy", "Copied"])
        self.assertEqual(code, 0)
        self.assertIn("Copied snippet #1 code to clipboard!", output)

    def test_copy_failure_falls_back_to_printing_code(self) -> None:
        """When the clipboard is unavailable the code itself is printed."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with contextlib.chdir(tmp_dir):
                self.capture_main(
                    ["add", "Printed", "--lang", "sh", "--code", "echo fallback"]
                )
                with mock.patch.object(
                    SnippetManager, "copy_to_clipboard", return_value=False
                ):
                    _, output = self.capture_main(["copy", "Printed"])
        self.assertIn("Could not access system clipboard", output)
        self.assertIn("echo fallback", output)

    def test_copy_missing_snippet_not_found(self) -> None:
        """Copying an unknown snippet reports it missing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with contextlib.chdir(tmp_dir):
                _, output = self.capture_main(["copy", "nope"])
        self.assertIn("Snippet not found.", output)

    def test_delete_reports_known_and_unknown_ids(self) -> None:
        """Delete confirms success and reports unknown IDs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with contextlib.chdir(tmp_dir):
                self.capture_main(["add", "Doomed", "--lang", "text", "--code", "bye"])
                _, deleted = self.capture_main(["delete", "1"])
                _, missing = self.capture_main(["delete", "99"])
        self.assertIn("Deleted snippet #1.", deleted)
        self.assertIn("Snippet ID not found.", missing)

    def test_dunder_main_exits_zero(self) -> None:
        """Executing main.py as a program lists from the scratch database."""
        entry = str(Path(__file__).resolve().parents[1] / "main.py")
        with tempfile.TemporaryDirectory() as tmp_dir:
            with contextlib.chdir(tmp_dir):
                argv = [entry, "list"]
                with mock.patch.object(sys, "argv", argv):
                    buffer = io.StringIO()
                    with contextlib.redirect_stdout(buffer):
                        with self.assertRaises(SystemExit) as ctx:
                            runpy.run_path(entry, run_name="__main__")
        self.assertEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
