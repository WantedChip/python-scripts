"""
Unit tests for Note Taker CLI.
"""

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict

from main import NoteStore, build_parser, export_note_as_markdown, main, render_preview


class TestNoteTaker(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.storage_file = self.temp_dir / "test_notes.json"
        self.store = NoteStore(self.storage_file)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_and_get_note(self):
        note = self.store.create_note("Test Note", "Body content", ["test", "unit"])
        self.assertIsNotNone(note["id"])
        self.assertEqual(note["title"], "Test Note")

        fetched = self.store.get_note(note["id"])
        self.assertEqual(fetched["body"], "Body content")

    def test_edit_note(self):
        note = self.store.create_note("Original Title", "Original Body")
        updated = self.store.edit_note(note["id"], title="New Title", tags=["updated"])
        self.assertEqual(updated["title"], "New Title")
        self.assertIn("updated", updated["tags"])

    def test_search_notes(self):
        self.store.create_note(
            "Python Tips", "Use type hints for better code", ["python"]
        )
        self.store.create_note("Cooking Recipe", "Bake bread at 200 degrees", ["food"])

        results = self.store.search_notes("hints")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Python Tips")

    def test_export_markdown(self):
        note = self.store.create_note("Export Test", "Markdown content", ["md"])
        out_path = self.temp_dir / "note.md"
        export_note_as_markdown(note, out_path)

        self.assertTrue(out_path.exists())
        content = out_path.read_text(encoding="utf-8")
        self.assertIn("# Export Test", content)
        self.assertIn("Markdown content", content)

    def test_render_preview(self):
        note = self.store.create_note("Preview Test", "Some text")
        preview = render_preview(note)
        self.assertIn("Preview Test", preview)


class TestNoteStoreEdgeCases(unittest.TestCase):
    """Test suite for storage robustness and remaining store operations."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))
        self.storage_file = self.temp_dir / "notes.json"
        self.store = NoteStore(self.storage_file)

    def test_corrupt_storage_file_returns_empty(self) -> None:
        self.storage_file.write_text("{not json", encoding="utf-8")
        self.assertEqual(self.store._load_notes(), [])

    def test_non_list_storage_returns_empty(self) -> None:
        self.storage_file.write_text('{"oops": true}', encoding="utf-8")
        self.assertEqual(self.store._load_notes(), [])

    def test_get_missing_note_returns_none(self) -> None:
        self.assertIsNone(self.store.get_note("zzzzzz"))

    def test_edit_updates_body_and_missing_id_fails(self) -> None:
        note = self.store.create_note("T", "old body")
        updated = self.store.edit_note(note["id"], body="brand new body")
        assert updated is not None
        self.assertEqual(updated["body"], "brand new body")
        self.assertIsNone(self.store.edit_note("missing", title="x"))

    def test_delete_note_reports_success_and_failure(self) -> None:
        note = self.store.create_note("Doomed", "bye")
        self.assertTrue(self.store.delete_note(note["id"]))
        self.assertFalse(self.store.delete_note(note["id"]))
        self.assertEqual(self.store._load_notes(), [])

    def test_list_notes_filters_by_tag_and_sorts_desc(self) -> None:
        first = self.store.create_note("First", "a", ["work"])
        self.store.create_note("Second", "b", ["home"])
        self.store.create_note("Third", "c", ["WORK"])

        listed = self.store.list_notes(tag_filter="work")
        titles = [n["title"] for n in listed]
        # Both work notes returned, most recently updated (Third) first.
        self.assertEqual(titles, ["Third", "First"])
        self.assertNotIn("Second", titles)
        self.assertEqual(len(self.store.list_notes()), 3)

        _ = first  # silence unused-variable lint

    def test_search_matches_body_and_tags_case_insensitive(self) -> None:
        self.store.create_note("Recipes", "Sourdough steps here", ["kitchen"])
        hits_body = self.store.search_notes("sourdough")
        self.assertEqual(len(hits_body), 1)
        hits_tag = self.store.search_notes("KITCHEN")
        self.assertEqual(len(hits_tag), 1)

    def test_export_creates_parent_folders(self) -> None:
        note: Dict[str, Any] = self.store.create_note("Deep", "content", ["md"])
        out_path = self.temp_dir / "nested" / "deeper" / "note.md"
        result = export_note_as_markdown(note, out_path)
        self.assertEqual(result, out_path)
        content = out_path.read_text(encoding="utf-8")
        self.assertIn("Tags: md", content)
        self.assertIn("---", content)

    def test_render_preview_without_tags_shows_empty_brackets(self) -> None:
        note = self.store.create_note("Plain", "text")
        preview = render_preview(note)
        self.assertIn("[]", preview)


class TestNoteCli(unittest.TestCase):
    """End-to-end tests for build_parser and the main() entry point."""

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))
        self.storage = self.temp_dir / "cli_notes.json"

    def _run(self, args: list) -> str:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["--file", str(self.storage)] + args)
        self.assertEqual(rc, 0)
        return buf.getvalue()

    def test_build_parser_add_and_export_subcommands(self) -> None:
        parser = build_parser()
        add_args = parser.parse_args(
            [
                "--file",
                "f.json",
                "add",
                "Title",
                "Body",
                "-t",
                "tag1",
                "tag2",
            ]
        )
        self.assertEqual(add_args.command, "add")
        self.assertEqual(add_args.tags, ["tag1", "tag2"])

        export_args = parser.parse_args(
            ["--file", "f.json", "export", "abc123", "-o", "out.md"]
        )
        self.assertEqual(export_args.output, Path("out.md"))
        with self.assertRaises(SystemExit):
            parser.parse_args(["--file", "f.json", "export", "abc123"])

    def test_full_note_lifecycle_via_cli(self) -> None:
        out = self._run(["add", "Groceries", "milk eggs", "-t", "shopping"])
        self.assertIn("Created note [", out)

        note_id = json.loads(self.storage.read_text(encoding="utf-8"))[0]["id"]

        listing = self._run(["list"])
        self.assertIn("--- Notes (1) ---", listing)
        self.assertIn("Groceries", listing)
        self.assertIn("[shopping]", listing)

        search_out = self._run(["search", "eggs"])
        self.assertIn("Groceries", search_out)

        edited = self._run(["edit", note_id, "--title", "Weekly shopping"])
        self.assertIn(f"Updated note [{note_id}].", edited)

        shown = self._run(["show", note_id])
        self.assertIn("Weekly shopping", shown)
        self.assertIn("milk eggs", shown)

        export_target = self.temp_dir / "note.md"
        exported = self._run(["export", note_id, "-o", str(export_target)])
        self.assertIn(f"Exported note [{note_id}] to {export_target}.", exported)
        self.assertTrue(export_target.exists())

        deleted = self._run(["delete", note_id])
        self.assertIn(f"Deleted note [{note_id}].", deleted)

    def test_cli_reports_missing_notes_for_id_operations(self) -> None:
        for subcmd in (
            ["edit", "nope00"],
            ["show", "nope00"],
            ["export", "nope00", "-o", str(self.temp_dir / "x.md")],
            ["delete", "nope00"],
        ):
            out = self._run(subcmd)
            self.assertIn("not found.", out)

    def test_default_list_command_prints_header(self) -> None:
        out = self._run(["list"])
        self.assertIn("--- Notes (0) ---", out)


if __name__ == "__main__":
    unittest.main()
