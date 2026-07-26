"""
Unit tests for Bookmark Manager CLI
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from main import Bookmark, BookmarkManager


class TestBookmarkModel(unittest.TestCase):
    def test_to_dict_and_from_dict(self) -> None:
        b = Bookmark(
            1, "https://example.com", "Example", "Description", ["test", "sample"]
        )
        d = b.to_dict()
        self.assertEqual(d["id"], 1)
        self.assertEqual(d["tags"], ["test", "sample"])

        reconstructed = Bookmark.from_dict(d)
        self.assertEqual(reconstructed.url, "https://example.com")
        self.assertEqual(reconstructed.title, "Example")


class TestBookmarkManager(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.file_path = os.path.join(self.temp_dir, "bookmarks.json")
        self.mgr = BookmarkManager(self.file_path)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def test_add_and_get_bookmark(self) -> None:
        b = self.mgr.add_bookmark(
            "https://python.org", "Python", "Docs", ["python", "dev"]
        )
        self.assertEqual(b.id, 1)
        self.assertEqual(len(self.mgr.bookmarks), 1)

        retrieved = self.mgr.get_bookmark(1)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.title, "Python")

    def test_update_and_delete_bookmark(self) -> None:
        b = self.mgr.add_bookmark("https://python.org", "Python")
        updated = self.mgr.update_bookmark(b.id, title="Python Org")
        self.assertEqual(updated.title, "Python Org")

        deleted = self.mgr.delete_bookmark(b.id)
        self.assertTrue(deleted)
        self.assertIsNone(self.mgr.get_bookmark(b.id))

    def test_filter_by_tag(self) -> None:
        self.mgr.add_bookmark("https://site1.com", "Site 1", tags=["web", "code"])
        self.mgr.add_bookmark("https://site2.com", "Site 2", tags=["web", "news"])
        self.mgr.add_bookmark("https://site3.com", "Site 3", tags=["games"])

        web_items = self.mgr.filter_by_tag("web")
        self.assertEqual(len(web_items), 2)

    def test_search(self) -> None:
        self.mgr.add_bookmark(
            "https://site1.com",
            "Machine Learning Guide",
            description="AI algorithms",
        )
        self.mgr.add_bookmark(
            "https://site2.com", "Cooking Recipes", description="Delicious food"
        )

        results = self.mgr.search("algorithms")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Machine Learning Guide")

    @patch("urllib.request.urlopen")
    def test_validate_link(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_response

        b = self.mgr.add_bookmark("https://example.com", "Example")
        status = self.mgr.validate_link(b)
        self.assertEqual(status, 200)
        self.assertEqual(b.last_status, 200)


if __name__ == "__main__":
    unittest.main()
