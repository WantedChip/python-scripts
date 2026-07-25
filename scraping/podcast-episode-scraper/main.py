"""Podcast Episode Scraper and RSS XML Parser.

Parses podcast RSS feeds to extract episode metadata (title, pub date,
duration, description, enclosure URL) and exports Markdown playlists or
downloads audio files locally.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments

import argparse
import os
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET  # nosec B405
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass
class PodcastEpisode:
    """Represents a single podcast episode."""

    title: str
    pub_date: str
    description: str
    duration: str
    audio_url: str
    episode_num: Optional[str] = None
    season_num: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert episode object to dictionary."""
        return asdict(self)


@dataclass
class PodcastFeed:
    """Represents a podcast channel feed."""

    title: str
    link: str
    description: str
    episodes: List[PodcastEpisode]


def parse_duration(raw_dur: Optional[str]) -> str:
    """Format raw duration (seconds or HH:MM:SS) into clean string."""
    if not raw_dur:
        return "Unknown"
    raw = raw_dur.strip()
    if ":" in raw:
        return raw
    if raw.isdigit():
        secs = int(raw)
        m, s = divmod(secs, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"
    return raw


def clean_html(text: str) -> str:
    """Strip HTML tags from text."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", "", text)
    return clean.strip()


def parse_podcast_rss(xml_content: str) -> PodcastFeed:
    """Parse RSS XML content into PodcastFeed structure."""
    try:
        root = ET.fromstring(xml_content)  # nosec B314
    except ET.ParseError as e:
        raise ValueError(f"Invalid RSS XML: {e}") from e

    channel = root.find("channel")
    if channel is None:
        raise ValueError("Invalid RSS: <channel> element not found")

    # XML Namespaces
    namespaces = {
        "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
        "content": "http://purl.org/rss/1.0/modules/content/",
    }

    feed_title = channel.findtext("title", "Untitled Podcast")
    feed_link = channel.findtext("link", "")
    feed_desc = clean_html(channel.findtext("description", ""))

    episodes: List[PodcastEpisode] = []

    for item in channel.findall("item"):
        title = item.findtext("title", "Untitled Episode")
        pub_date = item.findtext("pubDate", "")

        desc = item.findtext("description", "")
        itunes_summary = item.findtext("itunes:summary", namespaces=namespaces)
        if itunes_summary:
            desc = itunes_summary
        desc_clean = clean_html(desc)

        dur_raw = item.findtext("itunes:duration", namespaces=namespaces)
        duration = parse_duration(dur_raw)

        ep_num = item.findtext("itunes:episode", namespaces=namespaces)
        season_num = item.findtext("itunes:season", namespaces=namespaces)

        audio_url = ""
        enclosure = item.find("enclosure")
        if enclosure is not None:
            audio_url = enclosure.attrib.get("url", "")

        episodes.append(
            PodcastEpisode(
                title=title.strip(),
                pub_date=pub_date.strip(),
                description=desc_clean,
                duration=duration,
                audio_url=audio_url,
                episode_num=ep_num,
                season_num=season_num,
            )
        )

    return PodcastFeed(
        title=feed_title.strip(),
        link=feed_link.strip(),
        description=feed_desc,
        episodes=episodes,
    )


def export_markdown_playlist(
    feed: PodcastFeed, max_episodes: Optional[int] = None
) -> str:
    """Generate a Markdown playlist document for podcast episodes."""
    lines = [
        f"# {feed.title}",
        f"**Link:** [{feed.link}]({feed.link})" if feed.link else "",
        f"\n{feed.description}\n" if feed.description else "",
        "---",
        "## Episodes Playlist",
        "",
    ]

    episodes = feed.episodes[:max_episodes] if max_episodes else feed.episodes

    for idx, ep in enumerate(episodes, 1):
        if ep.season_num and ep.episode_num:
            prefix = f"S{ep.season_num}E{ep.episode_num} - "
        else:
            prefix = ""
        lines.append(f"### {idx}. {prefix}{ep.title}")
        lines.append(f"- **Published:** {ep.pub_date}")
        lines.append(f"- **Duration:** {ep.duration}")
        if ep.audio_url:
            lines.append(f"- **Direct Audio:** [Listen / Download]({ep.audio_url})")
        if ep.description:
            d_len = len(ep.description)
            snippet = ep.description[:250] + ("..." if d_len > 250 else "")
            lines.append(f"\n> {snippet}\n")
        lines.append("---")

    return "\n".join(lines)


def sanitize_filename(name: str) -> str:
    """Sanitize string for safe filesystem usage."""
    return re.sub(r'[\\/*?:"<>|]', "", name).replace(" ", "_")


def download_episodes(
    episodes: List[PodcastEpisode], output_dir: str, max_downloads: int = 3
) -> List[str]:
    """Download audio enclosures to specified output directory."""
    os.makedirs(output_dir, exist_ok=True)
    downloaded = []

    for idx, ep in enumerate(episodes[:max_downloads], 1):
        if not ep.audio_url:
            continue
        ext = ".mp3"
        if ".m4a" in ep.audio_url:
            ext = ".m4a"

        safe_title = sanitize_filename(ep.title)[:50]
        filename = f"{idx:02d}_{safe_title}{ext}"
        filepath = os.path.join(output_dir, filename)

        print(f"Downloading episode {idx}: {ep.title} -> {filepath}")
        headers = {"User-Agent": "Mozilla/5.0"}
        req = urllib.request.Request(ep.audio_url, headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:  # nosec B310
                with open(filepath, "wb") as f:
                    f.write(resp.read())
            downloaded.append(filepath)
        except (urllib.error.URLError, OSError, ValueError) as e:
            print(f"Failed to download {ep.title}: {e}", file=sys.stderr)

    return downloaded


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Parse podcast RSS feed and export playlist or download audio."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("--feed-url", help="Podcast RSS feed URL")
    parser.add_argument("--file", help="Local XML/RSS file path")
    parser.add_argument(
        "--max-episodes",
        type=int,
        help="Limit number of episodes to process",
    )
    parser.add_argument(
        "--search",
        help="Search keyword filter for episode titles/descriptions",
    )
    parser.add_argument("--export-md", help="Export Markdown playlist to filepath")
    parser.add_argument(
        "--download", action="store_true", help="Download audio files locally"
    )
    parser.add_argument(
        "--download-dir",
        default="podcast_downloads",
        help="Directory for downloaded audio",
    )
    parser.add_argument(
        "--max-downloads",
        type=int,
        default=3,
        help="Max episodes to download",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI Entry point for podcast-episode-scraper."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    xml_content = ""
    if parsed.file:
        with open(parsed.file, "r", encoding="utf-8") as f:
            xml_content = f.read()
    elif parsed.feed_url:
        headers = {"User-Agent": "Mozilla/5.0"}
        req = urllib.request.Request(parsed.feed_url, headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:  # nosec B310
                xml_content = resp.read().decode("utf-8")
        except (urllib.error.URLError, OSError, ValueError) as err:
            print(f"Error fetching feed URL: {err}", file=sys.stderr)
            return 1
    else:
        print("Please specify --feed-url or --file", file=sys.stderr)
        return 1

    feed = parse_podcast_rss(xml_content)

    if parsed.search:
        kw = parsed.search.lower()
        feed.episodes = [
            ep
            for ep in feed.episodes
            if kw in ep.title.lower() or kw in ep.description.lower()
        ]

    if parsed.max_episodes:
        feed.episodes = feed.episodes[: parsed.max_episodes]

    print(f"Parsed podcast: '{feed.title}' with {len(feed.episodes)} episodes.")

    if parsed.export_md:
        md_text = export_markdown_playlist(feed)
        with open(parsed.export_md, "w", encoding="utf-8") as f:
            f.write(md_text)
        print(f"Exported Markdown playlist to {parsed.export_md}")

    if parsed.download:
        dl_files = download_episodes(
            feed.episodes,
            parsed.download_dir,
            max_downloads=parsed.max_downloads,
        )
        print(f"Downloaded {len(dl_files)} audio files to {parsed.download_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
