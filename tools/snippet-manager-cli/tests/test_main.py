"""Unit tests for Snippet Manager CLI."""

import os
import tempfile
import unittest

from main import SnippetManager, format_snippet_display


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

    def test_list_with_language_filter(self) -> None:
        self.mgr.add_snippet("Py Quick", "python", "print('hi')")
        self.mgr.add_snippet("JS Quick", "javascript", "console.log('hi')")

        py_snippets = self.mgr.list_snippets(language="python")
        self.assertEqual(len(py_snippets), 1)
        self.assertEqual(py_snippets[0]["title"], "Py Quick")

    def test_search_snippets(self) -> None:
        self.mgr.add_snippet(
            "SQL Query", "sql", "SELECT * FROM users", tags="db,postgres"
        )
        results = self.mgr.search_snippets("postgres")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "SQL Query")

    def test_format_display(self) -> None:
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

    def test_delete_snippet(self) -> None:
        sid = self.mgr.add_snippet("To Delete", "text", "echo bye")
        self.assertTrue(self.mgr.delete_snippet(sid))
        self.assertIsNone(self.mgr.get_snippet(str(sid)))


if __name__ == "__main__":
    unittest.main()
