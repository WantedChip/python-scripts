"""
Unit tests for Note Taker CLI.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from main import NoteStore, export_note_as_markdown, render_preview


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


if __name__ == "__main__":
    unittest.main()
