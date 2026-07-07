"""Tests for link_checker.py."""

import json
import os
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

# Ensure the parent directory is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from link_checker import (
    LinkResult,
    build_summary,
    check_url,
    extract_links_from_html,
    extract_links_from_markdown,
    scan_local_files,
)


# ---------------------------------------------------------------------------
# extract_links_from_markdown
# ---------------------------------------------------------------------------
class TestExtractLinksFromMarkdown:
    def test_inline_link(self) -> None:
        content = "[Example](https://example.com)"
        links = extract_links_from_markdown(content, "test.md")
        assert ("https://example.com", "test.md") in links

    def test_reference_link(self) -> None:
        content = "[Example]: https://example.com"
        links = extract_links_from_markdown(content, "test.md")
        assert ("https://example.com", "test.md") in links

    def test_anchor_link_ignored(self) -> None:
        content = "[Top](#top)"
        links = extract_links_from_markdown(content, "test.md")
        assert links == []

    def test_multiple_links(self) -> None:
        content = "[A](https://a.com) and [B](https://b.com)"
        links = extract_links_from_markdown(content, "test.md")
        urls = [u for u, _ in links]
        assert "https://a.com" in urls
        assert "https://b.com" in urls

    def test_link_with_title_stripped(self) -> None:
        content = '[Foo](https://foo.com "Foo Title")'
        links = extract_links_from_markdown(content, "test.md")
        urls = [u for u, _ in links]
        assert "https://foo.com" in urls


# ---------------------------------------------------------------------------
# extract_links_from_html
# ---------------------------------------------------------------------------
class TestExtractLinksFromHtml:
    def test_href_link(self) -> None:
        html = '<a href="https://example.com">click</a>'
        links = extract_links_from_html(html, "https://page.com")
        assert ("https://example.com", "https://page.com") in links

    def test_relative_link_resolved(self) -> None:
        html = '<a href="/about">About</a>'
        links = extract_links_from_html(html, "https://example.com")
        urls = [u for u, _ in links]
        assert "https://example.com/about" in urls

    def test_javascript_ignored(self) -> None:
        html = '<a href="javascript:void(0)">JS</a>'
        links = extract_links_from_html(html, "https://example.com")
        assert links == []

    def test_anchor_ignored(self) -> None:
        html = '<a href="#section">Section</a>'
        links = extract_links_from_html(html, "https://example.com")
        assert links == []

    def test_src_link(self) -> None:
        html = '<img src="https://img.example.com/logo.png" />'
        links = extract_links_from_html(html, "https://example.com")
        assert ("https://img.example.com/logo.png", "https://example.com") in links


# ---------------------------------------------------------------------------
# check_url
# ---------------------------------------------------------------------------
class TestCheckUrl:
    def _make_response(
        self, status: int, url: str = "https://example.com"
    ) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status
        resp.url = url
        resp.headers = {"content-type": "text/html"}
        return resp

    @patch("link_checker.requests.Session")
    def test_ok_response(self, mock_session_cls: MagicMock) -> None:
        session = MagicMock()
        session.head.return_value = self._make_response(200)
        result = check_url("https://example.com", "test.md", session, 10)
        assert result.category == "ok"
        assert result.status_code == 200

    @patch("link_checker.requests.Session")
    def test_dead_404(self, mock_session_cls: MagicMock) -> None:
        session = MagicMock()
        session.head.return_value = self._make_response(404)
        result = check_url("https://example.com/missing", "test.md", session, 10)
        assert result.category == "dead"
        assert result.status_code == 404

    @patch("link_checker.requests.Session")
    def test_redirect(self, mock_session_cls: MagicMock) -> None:
        session = MagicMock()
        resp = self._make_response(301)
        resp.url = "https://example.com/new"
        session.head.return_value = resp
        result = check_url("https://example.com/old", "test.md", session, 10)
        assert result.category == "redirect"
        assert result.final_url == "https://example.com/new"

    @patch("link_checker.requests.Session")
    def test_timeout(self, mock_session_cls: MagicMock) -> None:
        session = MagicMock()
        session.head.side_effect = requests.exceptions.Timeout()
        result = check_url("https://slow.example.com", "test.md", session, 5)
        assert result.category == "timeout"
        assert result.status_code is None

    @patch("link_checker.requests.Session")
    def test_connection_error(self, mock_session_cls: MagicMock) -> None:
        session = MagicMock()
        session.head.side_effect = requests.exceptions.ConnectionError("refused")
        result = check_url("https://dead.example.com", "test.md", session, 10)
        assert result.category == "error"

    @patch("link_checker.requests.Session")
    def test_head_405_fallback_to_get(self, mock_session_cls: MagicMock) -> None:
        session = MagicMock()
        session.head.return_value = self._make_response(405)
        session.get.return_value = self._make_response(200)
        result = check_url("https://example.com", "test.md", session, 10)
        assert result.category == "ok"
        session.get.assert_called_once()


# ---------------------------------------------------------------------------
# build_summary
# ---------------------------------------------------------------------------
class TestBuildSummary:
    def _make_result(self, category: str) -> LinkResult:
        return LinkResult(
            url="https://example.com",
            status_code=200 if category == "ok" else None,
            category=category,
            final_url=None,
            error_message=None,
            source="test.md",
        )

    def test_counts(self) -> None:
        results = [
            self._make_result("ok"),
            self._make_result("ok"),
            self._make_result("dead"),
            self._make_result("redirect"),
            self._make_result("timeout"),
            self._make_result("error"),
        ]
        summary = build_summary(results)
        assert summary.total == 6
        assert summary.ok == 2
        assert summary.dead == 1
        assert summary.redirects == 1
        assert summary.timeouts == 1
        assert summary.errors == 1


# ---------------------------------------------------------------------------
# scan_local_files
# ---------------------------------------------------------------------------
class TestScanLocalFiles:
    def test_markdown_file_links(self, tmp_path: Path) -> None:
        md = tmp_path / "README.md"
        md.write_text("[Link](https://external.com)\n[Relative](./page.md)")
        links = scan_local_files(str(tmp_path), (".md",), None)
        urls = [u for u, _ in links]
        assert "https://external.com" in urls
        # Relative links without base_url are excluded
        assert all("./page.md" not in u for u in urls)

    def test_markdown_relative_with_base_url(self, tmp_path: Path) -> None:
        md = tmp_path / "docs.md"
        md.write_text("[Guide](./guide.md)")
        links = scan_local_files(str(tmp_path), (".md",), "https://example.com/docs/")
        urls = [u for u, _ in links]
        assert "https://example.com/docs/guide.md" in urls

    def test_html_file_links(self, tmp_path: Path) -> None:
        html = tmp_path / "index.html"
        html.write_text('<a href="https://example.com">Ex</a>')
        links = scan_local_files(str(tmp_path), (".html",), None)
        urls = [u for u, _ in links]
        assert "https://example.com" in urls
