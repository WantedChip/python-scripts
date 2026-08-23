import contextlib
import io
import os
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from typing import List
from unittest.mock import MagicMock, patch

from main import (
    PodcastEpisode,
    PodcastFeed,
    build_parser,
    clean_html,
    download_episodes,
    export_markdown_playlist,
    main,
    parse_duration,
    parse_podcast_rss,
    sanitize_filename,
)

RICH_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Polyglot Weekly</title>
    <link>https://example.com/polyglot</link>
    <description>Languages and tooling</description>
    <item>
      <title>Rust Compiler Deep Dive</title>
      <pubDate>Mon, 03 Aug 2026 09:00:00 GMT</pubDate>
      <description>Borrow checker mysteries revealed</description>
      <itunes:duration>2730</itunes:duration>
      <enclosure url="https://cdn.example.com/rust-deep-dive.mp3"
                 type="audio/mpeg" length="1000000"/>
    </item>
    <item>
      <title>Python Packaging Guide</title>
      <pubDate>Mon, 10 Aug 2026 09:00:00 GMT</pubDate>
      <description>Wheels, sdists and lockfiles</description>
      <itunes:duration>1980</itunes:duration>
      <enclosure url="https://cdn.example.com/packaging-guide.m4a"
                 type="audio/x-m4a" length="2000000"/>
    </item>
  </channel>
</rss>
"""


def _urlopen_bytes(data: bytes) -> MagicMock:
    """Build a mock urlopen return value serving raw bytes."""
    resp = MagicMock()
    resp.read.return_value = data
    resp.__enter__.return_value = resp
    return resp


SAMPLE_EPISODES: List[PodcastEpisode] = [
    PodcastEpisode(
        title="Episode 1: Intro",
        pub_date="Mon, 01 Jun 2026 10:00:00 GMT",
        description="First episode " + "with lots of detail. " * 30,
        duration="30:00",
        audio_url="https://example.com/ep1.mp3",
        episode_num="1",
        season_num="1",
    ),
    PodcastEpisode(
        title="Episode 2: Outro",
        pub_date="Mon, 08 Jun 2026 10:00:00 GMT",
        description="Second episode",
        duration="4512",
        audio_url="https://example.com/ep2.m4a",
    ),
]


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


class TestParsingHelpers(unittest.TestCase):
    """Duration / HTML helpers and RSS error handling."""

    def test_parse_duration_minutes_only(self) -> None:
        self.assertEqual(parse_duration("75"), "01:15")
        self.assertEqual(parse_duration("0"), "00:00")

    def test_parse_duration_passthrough_and_unknown(self) -> None:
        self.assertEqual(parse_duration("1:02:03"), "1:02:03")
        self.assertEqual(parse_duration("about an hour"), "about an hour")
        self.assertEqual(parse_duration(""), "Unknown")

    def test_clean_html_empty_string(self) -> None:
        self.assertEqual(clean_html(""), "")

    def test_parse_invalid_xml_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            parse_podcast_rss("<rss><unclosed>")

    def test_parse_missing_channel_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            parse_podcast_rss('<rss version="2.0"><other/></rss>')

    def test_episode_without_enclosure_or_itunes_fields(self) -> None:
        """Minimal items degrade gracefully to defaults."""
        rss = (
            '<?xml version="1.0"?><rss version="2.0"><channel>'
            "<title>Minimal</title><item></item></channel></rss>"
        )
        feed = parse_podcast_rss(rss)
        ep = feed.episodes[0]
        self.assertEqual(ep.title, "Untitled Episode")
        self.assertEqual(ep.duration, "Unknown")
        self.assertEqual(ep.audio_url, "")
        self.assertIsNone(ep.episode_num)
        self.assertIsNone(ep.season_num)

    def test_itunes_summary_overrides_description(self) -> None:
        rss = (
            '<?xml version="1.0"?>'
            '<rss version="2.0" '
            'xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">'
            "<channel><title>T</title>"
            "<item><description>RSS desc</description>"
            "<itunes:summary>Itunes summary wins</itunes:summary>"
            "</item></channel></rss>"
        )
        feed = parse_podcast_rss(rss)
        self.assertEqual(feed.episodes[0].description, "Itunes summary wins")


class TestMarkdownExport(unittest.TestCase):
    """Playlist rendering options."""

    def test_max_episodes_limits_output(self) -> None:
        feed = PodcastFeed(
            title="Feed", link="", description="", episodes=list(SAMPLE_EPISODES)
        )
        md = export_markdown_playlist(feed, max_episodes=1)
        self.assertIn("Episode 1: Intro", md)
        self.assertNotIn("Episode 2: Outro", md)

    def test_season_episode_prefix_rendered(self) -> None:
        feed = PodcastFeed(
            title="Feed", link="", description="", episodes=list(SAMPLE_EPISODES)
        )
        md = export_markdown_playlist(feed)
        self.assertIn("### 1. S1E1 - Episode 1: Intro", md)

    def test_episode_without_audio_has_no_download_link(self) -> None:
        no_audio = PodcastEpisode(
            title="Video Only", pub_date="", description="", duration="", audio_url=""
        )
        md = export_markdown_playlist(PodcastFeed("F", "", "", [no_audio]))
        self.assertNotIn("[Listen / Download]", md)

    def test_long_description_truncated_at_250_chars(self) -> None:
        long_desc = "x" * 400
        ep = PodcastEpisode(
            title="Long", pub_date="", description=long_desc, duration="", audio_url=""
        )
        md = export_markdown_playlist(PodcastFeed("F", "", "", [ep]))
        snippet_line = next(line for line in md.splitlines() if line.startswith("> "))
        self.assertTrue(snippet_line[2:].endswith("..."))
        self.assertLessEqual(len(snippet_line[2:]), 253)


class TestDownloadEpisodes(unittest.TestCase):
    """Audio enclosure downloads with mocked HTTP."""

    def test_downloads_write_files_with_correct_extensions(self) -> None:
        payload = b"\xff\xfb fake mp3 bytes"
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "main.urllib.request.urlopen",
                side_effect=[_urlopen_bytes(payload), _urlopen_bytes(payload)],
            ):
                downloaded = download_episodes(SAMPLE_EPISODES, tmpdir)
            self.assertEqual(len(downloaded), 2)
            names = sorted(os.path.basename(p) for p in downloaded)
            self.assertEqual(names[0], "01_Episode_1_Intro.mp3")
            # .m4a URL keeps its native extension.
            self.assertTrue(names[1].startswith("02_Episode_2_Outro.m4a"))
            with open(downloaded[0], "rb") as f:
                self.assertEqual(f.read(), payload)

    def test_download_failure_is_reported_not_raised(self) -> None:
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "main.urllib.request.urlopen",
                side_effect=urllib.error.URLError("refused"),
            ):
                with contextlib.redirect_stderr(err):
                    downloaded = download_episodes(SAMPLE_EPISODES[:1], tmpdir)
            self.assertEqual(downloaded, [])
            self.assertIn("Failed to download Episode 1: Intro", err.getvalue())

    def test_episodes_without_audio_are_skipped(self) -> None:
        no_audio = PodcastEpisode(
            title="No Audio", pub_date="", description="", duration="", audio_url=""
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            downloaded = download_episodes([no_audio], tmpdir)
        self.assertEqual(downloaded, [])


class TestPodcastCli(unittest.TestCase):
    """CLI-level tests for build_parser and main()."""

    def test_build_parser_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        self.assertIsNone(args.feed_url)
        self.assertIsNone(args.file)
        self.assertFalse(args.download)
        self.assertEqual(args.download_dir, "podcast_downloads")
        self.assertEqual(args.max_downloads, 3)

    def _write_feed(self, directory: str, name: str = "feed.xml") -> str:
        path = os.path.join(directory, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(RICH_RSS)
        return path

    def test_main_file_search_and_export_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            feed_path = self._write_feed(tmpdir)
            out_path = os.path.join(tmpdir, "playlist.md")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = main(
                    [
                        "--file",
                        feed_path,
                        "--search",
                        "rust",
                        "--export-md",
                        out_path,
                    ]
                )
            self.assertEqual(code, 0)
            out = buf.getvalue()
            self.assertIn("Parsed podcast: 'Polyglot Weekly' with 1 episodes.", out)
            self.assertIn(f"Exported Markdown playlist to {out_path}", out)
            with open(out_path, encoding="utf-8") as f:
                md = f.read()
            self.assertIn("Rust Compiler Deep Dive", md)
            self.assertNotIn("Python Packaging Guide", md)

    def test_main_requires_source(self) -> None:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = main([])
        self.assertEqual(code, 1)
        self.assertIn("--feed-url or --file", err.getvalue())

    def test_main_feed_url_error_returns_one(self) -> None:
        err = io.StringIO()
        with patch(
            "main.urllib.request.urlopen",
            side_effect=urllib.error.URLError("dns fail"),
        ):
            with contextlib.redirect_stderr(err):
                code = main(["--feed-url", "https://example.invalid/rss.xml"])
        self.assertEqual(code, 1)
        self.assertIn("Error fetching feed URL", err.getvalue())

    def test_main_download_writes_audio_files(self) -> None:
        payload = b"ID3 audio"
        with tempfile.TemporaryDirectory() as tmpdir:
            feed_path = self._write_feed(tmpdir, "dl.xml")
            dl_dir = os.path.join(tmpdir, "audio")
            buf = io.StringIO()
            with patch(
                "main.urllib.request.urlopen",
                side_effect=[_urlopen_bytes(payload), _urlopen_bytes(payload)],
            ):
                with redirect_stdout(buf):
                    code = main(
                        [
                            "--file",
                            feed_path,
                            "--download",
                            "--download-dir",
                            dl_dir,
                            "--max-downloads",
                            "2",
                        ]
                    )
            self.assertEqual(code, 0)
            self.assertIn("Downloaded 2 audio files", buf.getvalue())
            self.assertEqual(len(os.listdir(dl_dir)), 2)

    def test_to_dict_contains_all_fields(self) -> None:
        data = SAMPLE_EPISODES[0].to_dict()
        for key in (
            "title",
            "pub_date",
            "description",
            "duration",
            "audio_url",
            "episode_num",
            "season_num",
        ):
            self.assertIn(key, data)


if __name__ == "__main__":
    unittest.main()
