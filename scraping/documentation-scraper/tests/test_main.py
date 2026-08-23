"""Unit tests for Documentation Site Scraper."""

import contextlib
import io
import os
import tempfile
import unittest
import urllib.error
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from main import (
    DocPage,
    build_offline_html,
    build_offline_markdown,
    build_parser,
    crawl_docs,
    is_same_domain,
    main,
    parse_page_content,
    parse_sitemap,
)


def _urlopen_result(payload: str, status: int = 200) -> MagicMock:
    """Build a mock urlopen return value usable as a context manager."""
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = payload.encode("utf-8")
    resp.__enter__.return_value = resp
    return resp


def _fake_urlopen_factory(pages: Dict[str, str]) -> Any:
    """Return a urlopen stub serving canned HTML keyed by requested URL."""

    def _fake_urlopen(req: Any, timeout: int = 5) -> MagicMock:
        url = getattr(req, "full_url", req)
        if url not in pages:
            raise urllib.error.URLError(f"no fixture for {url}")
        return _urlopen_result(pages[url])

    return _fake_urlopen


class TestDocumentationScraper(unittest.TestCase):

    def setUp(self):
        self.sample_html = """<!DOCTYPE html>
<html>
<head><title>API Reference Documentation</title></head>
<body>
    <header><nav>Nav Bar Clutter <a href="/nav-link">Ignore</a></nav></header>
    <main>
        <h1>Welcome to API Docs</h1>
        <p>This is the main documentation content.</p>
        <a href="https://docs.example.com/guide">User Guide</a>
    </main>
    <footer>Copyright 2026</footer>
</body>
</html>"""

        self.sample_sitemap = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://docs.example.com/page1</loc></url>
  <url><loc>https://docs.example.com/page2</loc></url>
</urlset>"""

    def test_parse_page_content(self):
        title, content_html, content_text, links = parse_page_content(
            self.sample_html, "https://docs.example.com/index.html"
        )
        self.assertEqual(title, "API Reference Documentation")
        self.assertIn("Welcome to API Docs", content_text)
        self.assertNotIn("Nav Bar Clutter", content_text)
        self.assertNotIn("Copyright 2026", content_text)
        self.assertIn("https://docs.example.com/guide", links)

    def test_is_same_domain(self):
        self.assertTrue(
            is_same_domain("https://docs.example.com/page1", "docs.example.com")
        )
        self.assertFalse(
            is_same_domain("https://external.com/page1", "docs.example.com")
        )

    def test_parse_sitemap(self):
        urls = parse_sitemap(self.sample_sitemap)
        self.assertEqual(len(urls), 2)
        self.assertIn("https://docs.example.com/page1", urls)

    def test_build_offline_outputs(self):
        page1 = DocPage(
            "https://docs.example.com/p1",
            "Page 1",
            "<p>Content 1</p>",
            "Content 1",
            0,
        )
        page2 = DocPage(
            "https://docs.example.com/p2",
            "Page 2",
            "<p>Content 2</p>",
            "Content 2",
            1,
        )
        pages = [page1, page2]

        html_out = build_offline_html(pages, "Test Docs")
        self.assertIn("<title>Test Docs</title>", html_out)
        self.assertIn("Page 1", html_out)
        self.assertIn('href="#section-1"', html_out)

        md_out = build_offline_markdown(pages, "Test Docs")
        self.assertIn("# Test Docs", md_out)
        self.assertIn("1. [Page 1](#section-1)", md_out)


class TestParseSitemapEdgeCases(unittest.TestCase):
    """Robustness of sitemap XML parsing."""

    def test_parse_sitemap_malformed_xml_returns_empty(self) -> None:
        self.assertEqual(parse_sitemap("<urlset><unclosed>"), [])

    def test_parse_sitemap_ignores_loc_elements_without_text(self) -> None:
        xml = (
            '<?xml version="1.0"?><urlset>'
            "<url><loc></loc></url><url><loc>https://a.example/x</loc></url>"
            "</urlset>"
        )
        self.assertEqual(parse_sitemap(xml), ["https://a.example/x"])

    def test_is_same_domain_accepts_relative_urls(self) -> None:
        self.assertTrue(is_same_domain("/relative/path", "docs.example.com"))


class TestParsePageContentDetails(unittest.TestCase):
    """Content extraction details of the HTML parser."""

    def test_untitled_page_gets_placeholder_title(self) -> None:
        title, _, _, _ = parse_page_content(
            "<html><body><p>No title here</p></body></html>", "https://d.com/p"
        )
        self.assertEqual(title, "Untitled Documentation Page")

    def test_fragment_and_javascript_links_are_filtered(self) -> None:
        html = (
            "<main><a href='#anchor'>A</a><a href='javascript:void(0)'>B</a>"
            "<a href='/docs/page2'>C</a></main>"
        )
        links = parse_page_content(html, "https://d.com/index")[3]
        self.assertEqual(links, ["https://d.com/docs/page2"])

    def test_sidebar_class_content_is_skipped(self) -> None:
        html = (
            "<body><div class='sidebar'><p>Advert noise</p></div>"
            "<article class='content'><p>Real article body</p></article></body>"
        )
        _, _, text, _ = parse_page_content(html, "https://d.com/p")
        self.assertIn("Real article body", text)
        self.assertNotIn("Advert noise", text)


class TestCrawlDocs(unittest.TestCase):
    """BFS crawling behaviour with fully mocked HTTP responses."""

    PAGE_INDEX = (
        "<html><head><title>Docs Home</title></head><body>"
        "<nav>Menu junk <a href='https://ext.example.org/x'>External</a></nav>"
        "<main><h1>Home</h1>"
        "<a href='https://docs.example.com/guide'>Guide</a>"
        "<a href='#intro'>Anchor</a>"
        "</main></body></html>"
    )
    PAGE_GUIDE = (
        "<html><head><title>User Guide</title></head><body>"
        "<main><h1>Guide</h1>"
        "<a href='https://docs.example.com/#top'>Back home</a>"
        "</main></body></html>"
    )

    def test_crawl_follows_internal_links_only(self) -> None:
        pages_map = {
            "https://docs.example.com/": self.PAGE_INDEX,
            "https://docs.example.com/guide": self.PAGE_GUIDE,
        }
        with patch(
            "main.urllib.request.urlopen", side_effect=_fake_urlopen_factory(pages_map)
        ):
            pages = crawl_docs("https://docs.example.com/", max_depth=1)
        titles = [p.title for p in pages]
        self.assertEqual(titles, ["Docs Home", "User Guide"])
        self.assertEqual([p.depth for p in pages], [0, 1])

    def test_crawl_deduplicates_urls_with_fragments(self) -> None:
        pages_map = {
            "https://docs.example.com/": self.PAGE_INDEX,
            "https://docs.example.com/guide": self.PAGE_GUIDE,
        }
        with patch(
            "main.urllib.request.urlopen", side_effect=_fake_urlopen_factory(pages_map)
        ):
            pages = crawl_docs("https://docs.example.com/", max_depth=2)
        urls = [p.url for p in pages]
        self.assertEqual(len(urls), len(set(urls)))

    def test_crawl_respects_max_pages_limit(self) -> None:
        page = (
            "<html><head><title>P</title></head><body><main>"
            + "".join(
                f"<a href='https://docs.example.com/p{i}'>L{i}</a>" for i in range(5)
            )
            + "</main></body></html>"
        )
        pages_map = {"https://docs.example.com/": page}
        for i in range(5):
            pages_map[f"https://docs.example.com/p{i}"] = page
        with patch(
            "main.urllib.request.urlopen", side_effect=_fake_urlopen_factory(pages_map)
        ):
            pages = crawl_docs("https://docs.example.com/", max_depth=1, max_pages=2)
        self.assertEqual(len(pages), 2)

    def test_crawl_with_sitemap_seeds_queue(self) -> None:
        sitemap = (
            "<?xml version='1.0'?><urlset>"
            "<url><loc>https://docs.example.com/guide</loc></url>"
            "<url><loc>https://other.example.net/skip</loc></url>"
            "</urlset>"
        )
        guide = (
            "<html><head><title>Guide</title></head>"
            "<body><main><p>Guide text</p></main></body></html>"
        )
        with patch(
            "main.urllib.request.urlopen",
            side_effect=_fake_urlopen_factory(
                {"https://docs.example.com/guide": guide}
            ),
        ):
            pages = crawl_docs(
                "https://docs.example.com/",
                sitemap_xml=sitemap,
            )
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].title, "Guide")
        self.assertEqual(pages[0].depth, 0)

    def test_crawl_skips_pages_that_fail_to_download(self) -> None:
        with patch(
            "main.urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            pages = crawl_docs("https://docs.example.com/")
        self.assertEqual(pages, [])


class TestDocumentationCli(unittest.TestCase):
    """CLI-level tests for build_parser and main()."""

    def test_build_parser_defaults(self) -> None:
        args = build_parser().parse_args(["--root-url", "https://d.com/"])
        self.assertEqual(args.max_depth, 2)
        self.assertEqual(args.max_pages, 20)
        self.assertEqual(args.output_format, "html")
        self.assertEqual(args.output_file, "documentation_offline.html")

    def _run_main(self, argv: List[str]) -> tuple:
        """Run main() capturing stdout/stderr; return (code, out, err)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_main_reads_local_sitemap_and_writes_markdown(self) -> None:
        pages = [
            DocPage("https://docs.example.com/p1", "P1", "<p>c1</p>", "c1", 0),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            sitemap_path = os.path.join(tmpdir, "sitemap.xml")
            out_path = os.path.join(tmpdir, "offline.md")
            with open(sitemap_path, "w", encoding="utf-8") as f:
                f.write("<?xml version='1.0'?><urlset></urlset>")
            argv = [
                "--root-url",
                "https://docs.example.com/",
                "--sitemap",
                sitemap_path,
                "--output-format",
                "md",
                "--output-file",
                out_path,
            ]
            with patch("main.crawl_docs", return_value=pages) as mock_crawl:
                code, out, err = self._run_main(argv)
            self.assertEqual(code, 0)
            self.assertEqual(err, "")
            self.assertIn("Successfully scraped 1 documentation pages.", out)
            self.assertIn(f"Saved compiled offline reference to {out_path}", out)
            self.assertIn("urlset", mock_crawl.call_args.kwargs["sitemap_xml"])
            with open(out_path, encoding="utf-8") as f:
                saved = f.read()
            self.assertIn("# Offline Docs: https://docs.example.com/", saved)
            self.assertIn("## 1. P1", saved)

    def test_main_warns_when_remote_sitemap_unreachable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "offline.html")
            argv = [
                "--root-url",
                "https://docs.example.com/",
                "--sitemap",
                "https://cdn.example.net/sitemap.xml",
                "--output-file",
                out_path,
            ]
            with patch(
                "main.urllib.request.urlopen",
                side_effect=urllib.error.URLError("dns failure"),
            ):
                with patch("main.crawl_docs", return_value=[]):
                    code, out, err = self._run_main(argv)
            self.assertEqual(code, 0)
            self.assertIn("Warning: Failed to fetch sitemap:", err)
            self.assertIn("Successfully scraped 0 documentation pages.", out)


if __name__ == "__main__":
    unittest.main()
