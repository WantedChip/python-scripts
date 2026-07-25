import unittest

from main import filter_headlines, format_markdown, parse_rss_feed

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


if __name__ == "__main__":
    unittest.main()
