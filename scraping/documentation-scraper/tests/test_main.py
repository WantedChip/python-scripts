import unittest

from main import (
    DocPage,
    build_offline_html,
    build_offline_markdown,
    is_same_domain,
    parse_page_content,
    parse_sitemap,
)


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


if __name__ == "__main__":
    unittest.main()
