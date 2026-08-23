"""
Unit tests for Bookmark Manager CLI
"""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
import urllib.error
from typing import Any, List
from unittest.mock import MagicMock, patch

from main import Bookmark, BookmarkManager, main, print_bookmark


def _run_cli(args: List[str]) -> Any:
    """Runs ``main`` with redirected stdout; returns (exit_code, output)."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        exit_code = main(args)
    return exit_code, buffer.getvalue()


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

    def test_from_dict_defaults_missing_optional_fields(self) -> None:
        b = Bookmark.from_dict({"id": 7, "url": "u", "title": "t"})
        self.assertEqual(b.description, "")
        self.assertEqual(b.tags, [])
        self.assertIsNone(b.last_status)
        self.assertTrue(b.created_at)


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

    def test_load_corrupt_json_returns_empty_list(self) -> None:
        with open(self.file_path, "w", encoding="utf-8") as f:
            f.write("{not valid json")
        fresh_mgr = BookmarkManager(self.file_path)
        self.assertEqual(fresh_mgr.bookmarks, [])

    def test_persistence_roundtrip_keeps_all_fields(self) -> None:
        self.mgr.add_bookmark(
            "https://docs.python.org", "Docs", "Official docs", ["python"]
        )
        reloaded = BookmarkManager(self.file_path)
        self.assertEqual(len(reloaded.bookmarks), 1)
        stored = reloaded.bookmarks[0]
        self.assertEqual(stored.description, "Official docs")
        self.assertEqual(stored.tags, ["python"])

    def test_update_missing_id_returns_none(self) -> None:
        self.assertIsNone(self.mgr.update_bookmark(99, title="Ghost"))

    def test_delete_missing_id_returns_false_and_skips_save(self) -> None:
        with patch.object(self.mgr, "save") as mock_save:
            deleted = self.mgr.delete_bookmark(42)
        self.assertFalse(deleted)
        mock_save.assert_not_called()

    def test_ids_continue_after_deletion_of_lowest(self) -> None:
        first = self.mgr.add_bookmark("https://a.com", "A")
        second = self.mgr.add_bookmark("https://b.com", "B")
        self.assertEqual((first.id, second.id), (1, 2))
        self.mgr.delete_bookmark(first.id)
        third = self.mgr.add_bookmark("https://c.com", "C")
        self.assertEqual(third.id, 3)

    def test_filter_by_tag_is_case_insensitive_and_strips(self) -> None:
        self.mgr.add_bookmark("https://a.com", "A", tags=["Web"])
        matches = self.mgr.filter_by_tag("  WEB ")
        self.assertEqual(len(matches), 1)

    def test_search_matches_url_and_tags(self) -> None:
        by_url = self.mgr.add_bookmark("https://rustlang.org", "Rust")
        by_tag = self.mgr.add_bookmark("https://x.com", "X", tags=["kubernetes"])
        self.assertIn(by_url, self.mgr.search("rustlang"))
        self.assertIn(by_tag, self.mgr.search("kubern"))

    @patch("urllib.request.urlopen")
    def test_validate_all_records_statuses_and_saves(
        self, mock_urlopen: MagicMock
    ) -> None:
        response = MagicMock()
        response.status = 204
        mock_urlopen.return_value.__enter__.return_value = response
        b1 = self.mgr.add_bookmark("https://ok.com", "OK")
        results = self.mgr.validate_all()
        self.assertEqual(results[b1.id], 204)
        reloaded = BookmarkManager(self.file_path)
        self.assertEqual(reloaded.bookmarks[0].last_status, 204)

    @patch("main.webbrowser.open", return_value=True)
    def test_open_in_browser_delegates_to_webbrowser(
        self, mock_open: MagicMock
    ) -> None:
        self.assertTrue(BookmarkManager.open_in_browser("https://example.com"))
        mock_open.assert_called_once_with("https://example.com")


class TestValidateLinkFailurePaths(unittest.TestCase):
    """Tests for HTTP error handling and GET retry in validate_link."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.mgr = BookmarkManager(os.path.join(self.temp_dir, "b.json"))
        self.bookmark = self.mgr.add_bookmark("https://flaky.example", "Flaky")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    @patch("urllib.request.urlopen")
    def test_head_http_error_reports_code(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url=self.bookmark.url,
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )
        status = self.mgr.validate_link(self.bookmark)
        self.assertEqual(status, 404)

    @patch("urllib.request.urlopen")
    def test_head_failure_retries_with_get(self, mock_urlopen: MagicMock) -> None:
        get_response = MagicMock(status=200)
        get_response.__enter__.return_value = get_response
        mock_urlopen.side_effect = [
            urllib.error.URLError("HEAD rejected"),
            get_response,
        ]
        status = self.mgr.validate_link(self.bookmark)
        self.assertEqual(status, 200)
        self.assertEqual(mock_urlopen.call_count, 2)

    @patch("urllib.request.urlopen")
    def test_get_http_error_reports_code(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = [
            urllib.error.URLError("HEAD rejected"),
            urllib.error.HTTPError(
                url=self.bookmark.url,
                code=403,
                msg="Forbidden",
                hdrs=None,
                fp=None,
            ),
        ]
        status = self.mgr.validate_link(self.bookmark)
        self.assertEqual(status, 403)

    @patch("urllib.request.urlopen")
    def test_total_failure_returns_zero(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = [
            urllib.error.URLError("no dns"),
            urllib.error.URLError("still down"),
        ]
        status = self.mgr.validate_link(self.bookmark)
        self.assertEqual(status, 0)
        self.assertEqual(self.bookmark.last_status, 0)


class TestPrintBookmark(unittest.TestCase):
    """Tests for the formatted bookmark printer."""

    def _capture(self, bookmark: Bookmark) -> str:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            print_bookmark(bookmark)
        return buffer.getvalue()

    def test_full_details_rendered(self) -> None:
        b = Bookmark(3, "https://py.org", "Py", "Lang site", ["dev", "docs"])
        b.last_status = 200
        out = self._capture(b)
        self.assertIn("[3] Py [HTTP 200]", out)
        self.assertIn("URL : https://py.org", out)
        self.assertIn("Desc: Lang site", out)
        self.assertIn("Tags: dev, docs", out)

    def test_missing_description_and_status_render_placeholders(self) -> None:
        b = Bookmark(5, "https://x.io", "Bare")
        out = self._capture(b)
        self.assertNotIn("Desc:", out)
        self.assertNotIn("[HTTP", out)
        self.assertIn("Tags: None", out)


class TestCliCommands(unittest.TestCase):
    """End-to-end CLI tests; storage file is created inside a temp cwd."""

    def setUp(self) -> None:
        self.prev_cwd = os.getcwd()
        self.temp_dir = tempfile.mkdtemp()
        os.chdir(self.temp_dir)
        self.addCleanup(os.chdir, self.prev_cwd)
        self.addCleanup(shutil.rmtree, self.temp_dir, True)

    def test_add_then_list_roundtrip(self) -> None:
        code, out = _run_cli(
            [
                "add",
                "--url",
                "https://news.ycombinator.com",
                "--title",
                "HN",
                "--description",
                "Tech news",
                "--tags",
                "news, tech",
            ]
        )
        self.assertEqual(code, 0)
        self.assertIn("Added bookmark [1] 'HN'", out)
        self.assertTrue(os.path.exists("bookmarks.json"))

        code, out = _run_cli(["list"])
        self.assertIn("[1] HN", out)
        self.assertIn("Tags: news, tech", out)

        with open("bookmarks.json", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data[0]["url"], "https://news.ycombinator.com")

    def test_list_tag_filter_header_and_no_match_message(self) -> None:
        mgr = BookmarkManager("bookmarks.json")
        mgr.add_bookmark("https://a.com", "A", tags=["web"])
        code, out = _run_cli(["list", "--tag", "web"])
        self.assertIn("=== Bookmarks tagged with 'web' ===", out)
        code, out = _run_cli(["list", "--tag", "missing-tag"])
        self.assertIn("No bookmarks found.", out)

    def test_search_command_reports_matches_and_misses(self) -> None:
        mgr = BookmarkManager("bookmarks.json")
        mgr.add_bookmark("https://py.org", "Python Docs")
        _, out = _run_cli(["search", "python"])
        self.assertIn("Search results for 'python'", out)
        self.assertIn("Python Docs", out)
        _, out = _run_cli(["search", "zzz"])
        self.assertIn("No matching bookmarks found.", out)

    def test_update_command_edits_and_reports_unknown_id(self) -> None:
        mgr = BookmarkManager("bookmarks.json")
        added = mgr.add_bookmark("https://old.com", "Old")
        _, out = _run_cli(
            ["update", "--id", str(added.id), "--title", "New", "--url", "https://n.io"]
        )
        self.assertIn(f"Updated bookmark [{added.id}]", out)
        reloaded = BookmarkManager("bookmarks.json")
        self.assertEqual(reloaded.get_bookmark(added.id).url, "https://n.io")

        _, out = _run_cli(["update", "--id", "77", "--title", "Ghost"])
        self.assertIn("Bookmark with ID 77 not found.", out)

    def test_delete_command_removes_entry_or_reports_unknown_id(self) -> None:
        mgr = BookmarkManager("bookmarks.json")
        added = mgr.add_bookmark("https://gone.com", "Gone")
        _, out = _run_cli(["delete", "--id", str(added.id)])
        self.assertIn(f"Deleted bookmark [{added.id}]", out)
        reloaded = BookmarkManager("bookmarks.json")
        self.assertIsNone(reloaded.get_bookmark(added.id))

        _, out = _run_cli(["delete", "--id", "31"])
        self.assertIn("Bookmark with ID 31 not found.", out)

    @patch("urllib.request.urlopen")
    def test_validate_command_prints_per_link_status(
        self, mock_urlopen: MagicMock
    ) -> None:
        response = MagicMock()
        response.status = 503
        mock_urlopen.return_value.__enter__.return_value = response
        mgr = BookmarkManager("bookmarks.json")
        mgr.add_bookmark("https://degraded.io", "Degraded")

        _, out = _run_cli(["validate"])
        self.assertIn("Validating bookmark URLs...", out)
        self.assertIn("[1] Degraded: HTTP 503", out)

    @patch("urllib.request.urlopen")
    def test_validate_command_marks_dead_links(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = urllib.error.URLError("unreachable")
        mgr = BookmarkManager("bookmarks.json")
        mgr.add_bookmark("https://dead.zone", "Dead")

        _, out = _run_cli(["validate"])
        self.assertIn("[1] Dead: UNREACHABLE / DEAD LINK", out)

    @patch("main.webbrowser.open", return_value=True)
    def test_open_command_launches_browser_for_known_id(
        self, mock_open: MagicMock
    ) -> None:
        mgr = BookmarkManager("bookmarks.json")
        added = mgr.add_bookmark("https://launch.me", "Launch")
        _, out = _run_cli(["open", "--id", str(added.id)])
        self.assertIn("Opening 'https://launch.me' in browser...", out)
        mock_open.assert_called_once_with("https://launch.me")

        _, out = _run_cli(["open", "--id", "999"])
        self.assertIn("Bookmark with ID 999 not found.", out)

    def test_no_command_prints_help(self) -> None:
        _, out = _run_cli([])
        self.assertIn("usage:", out)


if __name__ == "__main__":
    unittest.main()
