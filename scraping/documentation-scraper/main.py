"""Documentation Site Scraper and Offline Reader Builder.

Crawls documentation pages from a root URL or sitemap, extracts main content
while stripping navigation and header/footer clutter, and builds a single-page
consolidated offline HTML or Markdown reference document with a Table of
Contents.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes

import argparse
import os
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET  # nosec B405
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import List, Optional, Set, Tuple


@dataclass
class DocPage:
    """Represents a crawled documentation page."""

    url: str
    title: str
    content_html: str
    content_text: str
    depth: int


CLUTTER_TAGS = {"nav", "header", "footer", "aside", "script", "style"}


class MainContentHTMLParser(HTMLParser):
    """Parses HTML to extract title, links, and main content."""

    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.in_title = False
        self.links: List[str] = []
        self.skip_depth = 0
        self.main_html_parts: List[str] = []
        self.main_text_parts: List[str] = []
        self.in_main = False
        self.main_depth = 0
        self.current_tag_stack: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attr_dict = {k: v or "" for k, v in attrs}
        tag_lower = tag.lower()
        self.current_tag_stack.append(tag_lower)

        if tag_lower == "title":
            self.in_title = True

        if tag_lower == "a" and "href" in attr_dict:
            href = attr_dict["href"]
            if not href.startswith("#") and not href.startswith("javascript:"):
                self.links.append(href)

        is_sidebar = "sidebar" in attr_dict.get("class", "").lower()
        if tag_lower in CLUTTER_TAGS or is_sidebar:
            self.skip_depth += 1

        is_content = "content" in attr_dict.get("class", "").lower()
        if tag_lower in ("main", "article") or is_content:
            if not self.in_main:
                self.in_main = True
                self.main_depth = len(self.current_tag_stack)

        if self.skip_depth == 0 and tag_lower not in CLUTTER_TAGS:
            attr_str = " ".join(f'{k}="{v}"' for k, v in attrs)
            attr_prefix = f" {attr_str}" if attr_str else ""
            self.main_html_parts.append(f"<{tag}{attr_prefix}>")

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower == "title":
            self.in_title = False

        if self.skip_depth == 0 and tag_lower not in CLUTTER_TAGS:
            self.main_html_parts.append(f"</{tag}>")

        if tag_lower in CLUTTER_TAGS or "sidebar" in tag_lower:
            if self.skip_depth > 0:
                self.skip_depth -= 1

        if self.in_main and len(self.current_tag_stack) == self.main_depth:
            self.in_main = False

        if self.current_tag_stack:
            self.current_tag_stack.pop()

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title += data
        if self.skip_depth == 0:
            self.main_html_parts.append(data)
            if data.strip():
                self.main_text_parts.append(data.strip())


def parse_page_content(html: str, url: str) -> Tuple[str, str, str, List[str]]:
    """Parses HTML content.

    Returns: (title, main_content_html, main_content_text, discovered_links)
    """
    parser = MainContentHTMLParser()
    parser.feed(html)
    title = parser.title.strip() or "Untitled Documentation Page"
    content_html = "".join(parser.main_html_parts).strip()
    content_text = "\n".join(parser.main_text_parts).strip()

    links = [urllib.parse.urljoin(url, href) for href in parser.links]
    return title, content_html, content_text, links


def is_same_domain(url: str, base_domain: str) -> bool:
    """Check if URL belongs to the target domain."""
    parsed = urllib.parse.urlparse(url)
    return parsed.netloc == base_domain or not parsed.netloc


def parse_sitemap(sitemap_xml: str) -> List[str]:
    """Extract URLs from a sitemap.xml string."""
    urls = []
    try:
        root = ET.fromstring(sitemap_xml)  # nosec B314
        for elem in root.iter():
            if elem.tag.endswith("loc") and elem.text:
                urls.append(elem.text.strip())
    except ET.ParseError:
        pass
    return urls


def crawl_docs(
    start_url: str,
    max_depth: int = 2,
    max_pages: int = 20,
    sitemap_xml: Optional[str] = None,
) -> List[DocPage]:
    """Crawl documentation pages starting from URL or sitemap."""
    base_parsed = urllib.parse.urlparse(start_url)
    base_domain = base_parsed.netloc

    visited: Set[str] = set()
    pages: List[DocPage] = []
    queue: List[Tuple[str, int]] = []

    if sitemap_xml:
        sitemap_urls = parse_sitemap(sitemap_xml)
        for u in sitemap_urls:
            queue.append((u, 0))
    else:
        queue.append((start_url, 0))

    while queue and len(pages) < max_pages:
        url, depth = queue.pop(0)

        # Normalize URL by removing fragments
        url_clean = urllib.parse.urldefrag(url)[0]
        if url_clean in visited:
            continue
        visited.add(url_clean)

        if not is_same_domain(url_clean, base_domain):
            continue

        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            req = urllib.request.Request(url_clean, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:  # nosec B310
                html = resp.read().decode("utf-8", errors="ignore")
        except (urllib.error.URLError, OSError, ValueError):
            continue

        res = parse_page_content(html, url_clean)
        title, content_html, content_text, found_links = res
        pages.append(
            DocPage(
                url=url_clean,
                title=title,
                content_html=content_html,
                content_text=content_text,
                depth=depth,
            )
        )

        if depth < max_depth:
            for link in found_links:
                link_clean = urllib.parse.urldefrag(link)[0]
                if link_clean not in visited and is_same_domain(
                    link_clean, base_domain
                ):
                    queue.append((link_clean, depth + 1))

    return pages


def build_offline_html(
    pages: List[DocPage], title: str = "Offline Documentation"
) -> str:
    """Build single consolidated HTML file with Table of Contents."""
    toc_items = []
    sections = []

    for idx, p in enumerate(pages, 1):
        anchor_id = f"section-{idx}"
        item_html = (
            f'<li><a href="#{anchor_id}">{p.title}</a> '
            f"<small>({p.url})</small></li>"
        )
        toc_items.append(item_html)

        sections.append(
            f"""
        <section id="{anchor_id}" class="doc-section">
            <h2>{idx}. {p.title}</h2>
            <p><small>Source: <a href="{p.url}" target="_blank">{p.url}</a></small></p>
            <hr>
            <div class="content">
                {p.content_html}
            </div>
        </section>
        """
        )

    toc_html = f"<ol>{''.join(toc_items)}</ol>"
    sections_html = "".join(sections)

    style_block = (
        "body { font-family: sans-serif; line-height: 1.6; "
        "max-width: 900px; margin: 0 auto; padding: 20px; color: #333; }\n"
        "h1 { border-bottom: 2px solid #333; padding-bottom: 10px; }\n"
        ".toc { background: #f8f9fa; border: 1px solid #e9ecef; "
        "padding: 15px 25px; border-radius: 6px; margin-bottom: 30px; }\n"
        ".doc-section { margin-top: 40px; padding-top: 20px; "
        "border-top: 1px solid #ddd; }\n"
        "code { background: #f1f3f5; padding: 2px 6px; border-radius: 4px; }\n"
        "pre { background: #212529; color: #f8f9fa; padding: 15px; "
        "border-radius: 6px; overflow-x: auto; }\n"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        {style_block}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <div class="toc">
        <h3>Table of Contents</h3>
        {toc_html}
    </div>
    <main>
        {sections_html}
    </main>
</body>
</html>"""


def build_offline_markdown(
    pages: List[DocPage], title: str = "Offline Documentation"
) -> str:
    """Build single consolidated Markdown file with Table of Contents."""
    lines = [f"# {title}", "", "## Table of Contents", ""]

    for idx, p in enumerate(pages, 1):
        anchor = f"section-{idx}"
        lines.append(f"{idx}. [{p.title}](#{anchor})")

    lines.append("\n---\n")

    for idx, p in enumerate(pages, 1):
        anchor = f"section-{idx}"
        lines.append(f"<a id='{anchor}'></a>")
        lines.append(f"## {idx}. {p.title}")
        lines.append(f"*Source: [{p.url}]({p.url})*\n")
        lines.append(p.content_text)
        lines.append("\n---\n")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Crawl documentation site and build offline reference file."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "--root-url",
        required=True,
        help="Root documentation URL to start crawling",
    )
    parser.add_argument("--sitemap", help="Optional sitemap XML file or URL")
    parser.add_argument(
        "--max-depth", type=int, default=2, help="Maximum crawling depth"
    )
    parser.add_argument("--max-pages", type=int, default=20, help="Maximum pages limit")
    parser.add_argument(
        "--output-format",
        choices=["html", "md"],
        default="html",
        help="Output file format",
    )
    parser.add_argument(
        "--output-file",
        default="documentation_offline.html",
        help="Output filepath",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI Entry point for documentation-scraper."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    sitemap_xml = None
    if parsed.sitemap:
        if os.path.exists(parsed.sitemap):
            with open(parsed.sitemap, "r", encoding="utf-8") as f:
                sitemap_xml = f.read()
        else:
            try:
                headers = {"User-Agent": "Mozilla/5.0"}
                req = urllib.request.Request(parsed.sitemap, headers=headers)
                with urllib.request.urlopen(req) as resp:  # nosec B310
                    sitemap_xml = resp.read().decode("utf-8")
            except (urllib.error.URLError, OSError, ValueError) as err:
                print(f"Warning: Failed to fetch sitemap: {err}", file=sys.stderr)

    msg = (
        f"Crawling documentation from {parsed.root_url} "
        f"(Max Depth: {parsed.max_depth}, Max Pages: {parsed.max_pages})..."
    )
    print(msg)
    pages = crawl_docs(
        start_url=parsed.root_url,
        max_depth=parsed.max_depth,
        max_pages=parsed.max_pages,
        sitemap_xml=sitemap_xml,
    )

    print(f"Successfully scraped {len(pages)} documentation pages.")

    if parsed.output_format == "html":
        out_content = build_offline_html(
            pages, title=f"Offline Docs: {parsed.root_url}"
        )
    else:
        out_content = build_offline_markdown(
            pages, title=f"Offline Docs: {parsed.root_url}"
        )

    with open(parsed.output_file, "w", encoding="utf-8") as f:
        f.write(out_content)

    print(f"Saved compiled offline reference to {parsed.output_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
