import contextlib
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from main import (
    build_parser,
    fetch_url_content,
    filter_headlines,
    format_markdown,
    main,
    parse_html_headlines,
    parse_rss_feed,
)

SAMPLE_RSS_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
<channel>
 <title>Sample Tech Feed</title>
 <description>Sample feed for testing</description>
 <item>
  <title>Python 3.12 Released with Better Performance</title>
  <link>https://example.com/python-312</link>
  <description>New release features major performance gains.</description>
  <pubDate>Mon, 24 Jul 2026 12:00:00 GMT</pubDate>
 </item>
 <item>
  <title>SpaceX Launches New Satellite Constellation</title>
  <link>https://example.com/spacex-launch</link>
  <description>Another successful launch into orbit.</description>
  <pubDate>Mon, 24 Jul 2026 14:00:00 GMT</pubDate>
 </item>
</channel>
</rss>
"""

SAMPLE_ATOM_XML = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Example Feed</title>
  <entry>
    <title>Atom Entry About Rust and WebAssembly</title>
    <link rel="alternate" href="https://example.com/atom-entry"/>
    <summary>Rust keeps winning over systems developers.</summary>
    <published>2026-08-01T10:00:00Z</published>
  </entry>
</feed>
"""


class TestNewsHeadlineScraper(unittest.TestCase):
    """Unit tests for News Headline Scraper."""

    def test_parse_rss_feed(self) -> None:
        headlines = parse_rss_feed(SAMPLE_RSS_XML)
        self.assertEqual(len(headlines), 2)
        expected_title = "Python 3.12 Released with Better Performance"
        self.assertEqual(headlines[0]["title"], expected_title)
        self.assertEqual(headlines[0]["link"], "https://example.com/python-312")

    def test_filter_headlines(self) -> None:
        headlines = parse_rss_feed(SAMPLE_RSS_XML)
        filtered = filter_headlines(headlines, keyword="Python")
        self.assertEqual(len(filtered), 1)
        self.assertIn("Python", filtered[0]["title"])

        filtered_empty = filter_headlines(headlines, keyword="NonExistentKeyword")
        self.assertEqual(len(filtered_empty), 0)

    def test_format_markdown(self) -> None:
        headlines = parse_rss_feed(SAMPLE_RSS_XML)
        md = format_markdown(headlines, title="Test Headlines")
        self.assertIn("# Test Headlines", md)
        link_str = (
            "[Python 3.12 Released with Better Performance]"
            "(https://example.com/python-312)"
        )
        self.assertIn(link_str, md)


class TestParseRssFeedEdgeCases(unittest.TestCase):
    """Feed parsing edge cases: Atom, malformed XML, missing fields."""

    def test_parse_atom_feed_with_namespaced_links(self) -> None:
        """Atom entries are recognized via namespaced tags and href attrs."""
        headlines = parse_rss_feed(SAMPLE_ATOM_XML)
        self.assertEqual(len(headlines), 1)
        entry = headlines[0]
        self.assertEqual(entry["title"], "Atom Entry About Rust and WebAssembly")
        self.assertEqual(entry["link"], "https://example.com/atom-entry")
        self.assertEqual(
            entry["description"], "Rust keeps winning over systems developers."
        )
        self.assertEqual(entry["pub_date"], "2026-08-01T10:00:00Z")

    def test_parse_malformed_xml_returns_empty_list(self) -> None:
        self.assertEqual(parse_rss_feed("<not-valid-xml"), [])

    def test_item_without_title_gets_placeholder(self) -> None:
        """Items lacking a title fall back to the 'No Title' placeholder."""
        xml = (
            '<rss version="2.0"><channel><item>'
            "<link>https://example.com/x</link>"
            "</item></channel></rss>"
        )
        headlines = parse_rss_feed(xml)
        self.assertEqual(len(headlines), 1)
        self.assertEqual(headlines[0]["title"], "No Title")

    def test_atom_link_without_href_uses_text(self) -> None:
        """An RSS-style textual link is used when href attribute is absent."""
        xml = (
            '<rss version="2.0"><channel><item>'
            "<title>A Headline With Enough Words Here</title>"
            "<link>https://example.com/text-link</link>"
            "</item></channel></rss>"
        )
        headlines = parse_rss_feed(xml)
        self.assertEqual(headlines[0]["link"], "https://example.com/text-link")


class TestFilterAndFormat(unittest.TestCase):
    """Keyword filtering and Markdown formatting behavior."""

    def _headlines(self) -> List[Dict[str, str]]:
        return [
            {
                "title": "Release Announcement",
                "link": "https://example.com/a",
                "description": "Mentions Python internals",
                "pub_date": "",
            },
            {"title": "Unrelated Story", "link": "", "description": "", "pub_date": ""},
        ]

    def test_filter_matches_description_case_insensitive(self) -> None:
        filtered = filter_headlines(self._headlines(), keyword="PYTHON")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["title"], "Release Announcement")

    def test_filter_without_keyword_returns_all(self) -> None:
        self.assertEqual(len(filter_headlines(self._headlines())), 2)

    def test_format_markdown_empty_link_and_missing_fields(self) -> None:
        """Missing link renders '#' and absent date/description are omitted."""
        md = format_markdown(
            [{"title": "Only Title", "link": "", "description": "", "pub_date": ""}],
            title="Digest",
        )
        self.assertIn("[Only Title](#)", md)
        self.assertNotIn("Published:", md)
        self.assertNotIn("> ", md)


class TestHtmlHeadlineExtraction(unittest.TestCase):
    """BeautifulSoup-based HTML fallback extractor."""

    def test_parse_html_headlines_filters_short_text(self) -> None:
        html = """
        <html><body>
            <h2>Major Breakthrough In Quantum Computing Announced</h2>
            <a href="/short">tiny</a>
            <a href="/long-enough">A Reasonably Long Anchor Text Link</a>
        </body></html>
        """
        headlines = parse_html_headlines(html)
        titles = [h["title"] for h in headlines]
        self.assertIn("Major Breakthrough In Quantum Computing Announced", titles)
        self.assertIn("A Reasonably Long Anchor Text Link", titles)
        # Short anchor text is dropped by the >15 char heuristic.
        self.assertNotIn("tiny", titles)
        linked = [h for h in headlines if h["title"].startswith("A Reasonably")]
        self.assertEqual(linked[0]["link"], "/long-enough")


class TestFetchUrlContent(unittest.TestCase):
    """Content loading from local files and remote URLs."""

    def test_fetch_local_file(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".xml", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(SAMPLE_RSS_XML)
            path = tmp.name
        try:
            self.assertEqual(fetch_url_content(path), SAMPLE_RSS_XML)
        finally:
            os.remove(path)

    def test_fetch_remote_via_requests(self) -> None:
        response = MagicMock()
        response.text = "<html>remote body</html>"
        with patch("main.requests.get", return_value=response) as mock_get:
            content = fetch_url_content("https://example.com/feed")
        self.assertEqual(content, "<html>remote body</html>")
        _, kwargs = mock_get.call_args
        self.assertIn("User-Agent", kwargs["headers"])


class TestNewsHeadlineCli(unittest.TestCase):
    """CLI-level tests for build_parser and main()."""

    def test_build_parser_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        self.assertEqual(args.url, "https://news.ycombinator.com/rss")
        self.assertIsNone(args.keyword)
        self.assertEqual(args.limit, 10)
        self.assertIsNone(args.output)
        self.assertIsNone(args.format)

    def test_main_reads_local_rss_and_prints_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            feed_path = os.path.join(tmpdir, "feed.xml")
            with open(feed_path, "w", encoding="utf-8") as f:
                f.write(SAMPLE_RSS_XML)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(["--url", feed_path])
            self.assertEqual(code, 0)
            out = buf.getvalue()
            self.assertIn("# News Headlines Summary", out)
            self.assertIn("Python 3.12 Released", out)

    def test_main_keyword_limit_and_json_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            feed_path = os.path.join(tmpdir, "feed.xml")
            out_path = os.path.join(tmpdir, "digest.json")
            with open(feed_path, "w", encoding="utf-8") as f:
                f.write(SAMPLE_RSS_XML)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(
                    [
                        "--url",
                        feed_path,
                        "-k",
                        "spacex",
                        "--limit",
                        "5",
                        "-o",
                        out_path,
                    ]
                )
            self.assertEqual(code, 0)
            self.assertIn(f"Saved 1 headlines to {out_path}", buf.getvalue())
            with open(out_path, encoding="utf-8") as f:
                saved: Any = json.load(f)
            self.assertIsInstance(saved, list)
            self.assertIn("SpaceX", saved[0]["title"])

    def test_main_unreachable_source_returns_error(self) -> None:
        """A nonexistent local path surfaces a fetch error exit code."""
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = main(["--url", "Z:/definitely/missing/path.xml"])
        self.assertEqual(code, 1)
        self.assertIn("Error fetching content", err.getvalue())


if __name__ == "__main__":
    unittest.main()
