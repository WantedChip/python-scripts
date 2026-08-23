"""News Headline Scraper CLI.

Scrapes top news headlines from RSS/Atom feeds or news web pages,
supports keyword filtering, and exports to Markdown or JSON.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET  # nosec B405
from typing import Dict, List, Optional

try:
    import requests
    from bs4 import BeautifulSoup

    HAS_SCRAPE_LIBS = True
except ImportError:
    requests = None  # type: ignore[assignment]
    BeautifulSoup = None  # type: ignore[assignment,misc]
    HAS_SCRAPE_LIBS = False


def fetch_url_content(url: str, timeout: int = 10) -> str:
    """Fetch content from HTTP/HTTPS URL or local file path.

    Args:
        url: Remote URL or local file path.
        timeout: Request timeout in seconds.

    Returns:
        String content of response or file.
    """
    if os.path.isfile(url):
        with open(url, "r", encoding="utf-8") as f:
            return f.read()

    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " + "NewsHeadlineScraper/1.0"
    if HAS_SCRAPE_LIBS and requests:
        headers = {"User-Agent": ua}
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.text

    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec B310
        return str(response.read().decode("utf-8"))


def _find_first_child(item: ET.Element, *paths: str) -> Optional[ET.Element]:
    """Return the first existing child element among the given tag paths."""
    for path in paths:
        elem = item.find(path)
        if elem is not None:
            return elem
    return None


def parse_rss_feed(xml_content: str) -> List[Dict[str, str]]:
    """Parse RSS/Atom XML string to extract headlines.

    Args:
        xml_content: Raw XML feed content string.

    Returns:
        List of dictionaries containing title, link, description, and date.
    """
    headlines = []
    try:
        root = ET.fromstring(xml_content)  # nosec B314
        # Standard RSS 2.0 channel -> item
        channel = root.find("channel")
        items = channel.findall("item") if channel is not None else []

        if not items:
            # Check Atom feed entries <entry>
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            items = root.findall("atom:entry", ns) or root.findall("entry")

        for item in items:
            t_atom = "{http://www.w3.org/2005/Atom}title"
            title_elem = _find_first_child(item, "title", t_atom)
            l_atom = "{http://www.w3.org/2005/Atom}link"
            link_elem = _find_first_child(item, "link", l_atom)
            d_atom = "{http://www.w3.org/2005/Atom}summary"
            desc_elem = _find_first_child(item, "description", "summary", d_atom)
            p_atom = "{http://www.w3.org/2005/Atom}published"
            date_elem = _find_first_child(item, "pubDate", "published", p_atom)

            title = (
                title_elem.text.strip()
                if title_elem is not None and title_elem.text
                else "No Title"
            )
            link = ""
            if link_elem is not None:
                l_text = (link_elem.text or "").strip()
                link = link_elem.attrib.get("href") or l_text
            desc = (
                desc_elem.text.strip()
                if desc_elem is not None and desc_elem.text
                else ""
            )
            pub_date = (
                date_elem.text.strip()
                if date_elem is not None and date_elem.text
                else ""
            )

            headlines.append(
                {
                    "title": title,
                    "link": link,
                    "description": desc,
                    "pub_date": pub_date,
                }
            )
    except ET.ParseError:
        pass
    return headlines


def parse_html_headlines(html_content: str) -> List[Dict[str, str]]:
    """Fallback HTML headline extractor using BeautifulSoup or regex.

    Args:
        html_content: Raw HTML content.

    Returns:
        List of dictionaries containing title and link.
    """
    headlines: List[Dict[str, str]] = []
    if HAS_SCRAPE_LIBS and BeautifulSoup is not None:
        soup = BeautifulSoup(html_content, "html.parser")
        for tag in soup.find_all(["h1", "h2", "h3", "a"]):
            text = tag.get_text().strip()
            href_attr = tag.get("href", "") if tag.name == "a" else ""
            link = str(href_attr)
            if len(text) > 15 and (" " in text):
                headlines.append(
                    {
                        "title": text,
                        "link": link,
                        "description": "",
                        "pub_date": "",
                    }
                )
    return headlines


def filter_headlines(
    headlines: List[Dict[str, str]], keyword: Optional[str] = None
) -> List[Dict[str, str]]:
    """Filter headlines by keyword (case-insensitive).

    Args:
        headlines: List of headline dictionaries.
        keyword: Substring filter.

    Returns:
        Filtered list of headline dictionaries.
    """
    if not keyword:
        return headlines

    kw = keyword.lower()
    return [
        h
        for h in headlines
        if kw in h["title"].lower() or kw in h["description"].lower()
    ]


def format_markdown(
    headlines: List[Dict[str, str]], title: str = "News Headlines Summary"
) -> str:
    """Format headline list into Markdown document string.

    Args:
        headlines: List of headline dicts.
        title: Document header title.

    Returns:
        Markdown string.
    """
    lines = [f"# {title}", "", f"Total Headlines: {len(headlines)}", ""]
    for i, h in enumerate(headlines, start=1):
        lines.append(f"### {i}. [{h['title']}]({h['link'] or '#'})")
        if h["pub_date"]:
            lines.append(f"*Published: {h['pub_date']}*")
        if h["description"]:
            lines.append(f"> {h['description']}")
        lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Scrape news headlines from RSS feeds or websites."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "--url",
        default="https://news.ycombinator.com/rss",
        help="Feed or site URL / file path",
    )
    parser.add_argument("-k", "--keyword", help="Filter headlines by keyword")
    parser.add_argument(
        "-l",
        "--limit",
        type=int,
        default=10,
        help="Maximum number of headlines to return",
    )
    parser.add_argument("-o", "--output", help="Output file path (.md or .json)")
    parser.add_argument(
        "-f", "--format", choices=["markdown", "json"], help="Force output format"
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for news headline scraper."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    print(f"Fetching headlines from: {parsed.url} ...")
    try:
        raw_content = fetch_url_content(parsed.url)
    except (urllib.error.URLError, OSError, ValueError) as err:
        print(f"Error fetching content: {err}", file=sys.stderr)
        return 1

    headlines = parse_rss_feed(raw_content)
    if not headlines and HAS_SCRAPE_LIBS:
        headlines = parse_html_headlines(raw_content)

    headlines = filter_headlines(headlines, keyword=parsed.keyword)[: parsed.limit]

    fmt = parsed.format
    if not fmt and parsed.output:
        fmt = "json" if parsed.output.endswith(".json") else "markdown"
    elif not fmt:
        fmt = "markdown"

    if fmt == "json":
        output_data = json.dumps(headlines, indent=2)
    else:
        output_data = format_markdown(headlines)

    if parsed.output:
        with open(parsed.output, "w", encoding="utf-8") as f:
            f.write(output_data)
        print(f"Saved {len(headlines)} headlines to {parsed.output}")
    else:
        print(output_data)

    return 0


if __name__ == "__main__":
    sys.exit(main())
