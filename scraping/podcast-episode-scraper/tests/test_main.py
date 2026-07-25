import unittest

from main import (
    clean_html,
    export_markdown_playlist,
    parse_duration,
    parse_podcast_rss,
    sanitize_filename,
)


class TestPodcastEpisodeScraper(unittest.TestCase):

    def setUp(self):
        self.sample_rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>The Python Developer Podcast</title>
    <link>https://example.com/podcast</link>
    <description>&lt;p&gt;A podcast about Python engineering&lt;/p&gt;</description>
    <item>
      <title>Episode 42: Asyncio Best Practices</title>
      <pubDate>Mon, 20 Jul 2026 14:00:00 GMT</pubDate>
      <description>&lt;p&gt;Deep dive into Python asyncio loops&lt;/p&gt;</description>
      <itunes:duration>3605</itunes:duration>
      <itunes:episode>42</itunes:episode>
      <itunes:season>2</itunes:season>
      <enclosure url="https://example.com/audio/ep42.mp3"
                 type="audio/mpeg" length="12345678"/>
    </item>
  </channel>
</rss>
"""

    def test_parse_duration(self):
        self.assertEqual(parse_duration("3605"), "01:00:05")
        self.assertEqual(parse_duration("45:30"), "45:30")
        self.assertEqual(parse_duration(None), "Unknown")

    def test_clean_html(self):
        self.assertEqual(clean_html("<p>Hello <b>World</b></p>"), "Hello World")

    def test_parse_podcast_rss(self):
        feed = parse_podcast_rss(self.sample_rss)
        self.assertEqual(feed.title, "The Python Developer Podcast")
        self.assertEqual(feed.link, "https://example.com/podcast")
        self.assertEqual(len(feed.episodes), 1)

        ep = feed.episodes[0]
        self.assertEqual(ep.title, "Episode 42: Asyncio Best Practices")
        self.assertEqual(ep.duration, "01:00:05")
        self.assertEqual(ep.episode_num, "42")
        self.assertEqual(ep.season_num, "2")
        self.assertEqual(ep.audio_url, "https://example.com/audio/ep42.mp3")

    def test_export_markdown_playlist(self):
        feed = parse_podcast_rss(self.sample_rss)
        md = export_markdown_playlist(feed)
        self.assertIn("# The Python Developer Podcast", md)
        self.assertIn("Episode 42: Asyncio Best Practices", md)
        self.assertIn("[Listen / Download](https://example.com/audio/ep42.mp3)", md)

    def test_sanitize_filename(self):
        self.assertEqual(
            sanitize_filename("Ep 42: Asyncio? Yes!"), "Ep_42_Asyncio_Yes!"
        )


if __name__ == "__main__":
    unittest.main()
