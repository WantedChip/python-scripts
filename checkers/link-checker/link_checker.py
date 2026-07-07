#!/usr/bin/env python3
"""Broken Link Checker.

Crawls a website URL or scans local Markdown/HTML files, reporting
dead links (4xx/5xx), redirects (3xx), timeouts, and connection errors.
Supports concurrent checking via a thread pool.
"""

import argparse
import collections
import concurrent.futures
import csv
import json
import logging
import os
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_TIMEOUT: int = 10
DEFAULT_WORKERS: int = 10
DEFAULT_MAX_DEPTH: int = 3
DEFAULT_USER_AGENT: str = "LinkChecker/1.0 (github.com/WantedChip/python-scripts)"

# Regex patterns for extracting links
MD_LINK_RE = re.compile(r"\[(?:[^\]]*)\]\(([^)]+)\)")
MD_REF_RE = re.compile(r"^\[(?:[^\]]*)\]:\s*(\S+)", re.MULTILINE)
HTML_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
HTML_SRC_RE = re.compile(r'src=["\']([^"\']+)["\']', re.IGNORECASE)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
@dataclass
class LinkResult:
    """Result of checking a single link.

    Attributes:
        url: The URL that was checked.
        status_code: HTTP status code, or None on network error.
        category: Classification (ok, redirect, dead, timeout, error).
        final_url: The final URL after redirects, if applicable.
        error_message: Human-readable error description, if applicable.
        source: File or page where this link was found.
    """

    url: str
    status_code: Optional[int]
    category: str  # ok | redirect | dead | timeout | error
    final_url: Optional[str]
    error_message: Optional[str]
    source: str


@dataclass
class CheckSummary:
    """Aggregated summary of a link-checking run.

    Attributes:
        total: Total links checked.
        ok: Links returning 2xx.
        redirects: Links returning 3xx.
        dead: Links returning 4xx/5xx.
        timeouts: Links that timed out.
        errors: Links with connection/other errors.
        results: All individual link results.
    """

    total: int = 0
    ok: int = 0
    redirects: int = 0
    dead: int = 0
    timeouts: int = 0
    errors: int = 0
    results: List[LinkResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def build_session(user_agent: str, timeout: int) -> requests.Session:
    """Build a requests Session with retry logic and custom headers.

    Args:
        user_agent: User-Agent string to send.
        timeout: Default request timeout in seconds.

    Returns:
        Configured requests Session.
    """
    session = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": user_agent})
    return session


def check_url(
    url: str,
    source: str,
    session: requests.Session,
    timeout: int,
) -> LinkResult:
    """Check a single URL and return its result.

    First attempts HEAD (cheaper), falls back to GET if HEAD is rejected.

    Args:
        url: URL to check.
        source: Where the link was found (file path or page URL).
        session: Shared requests Session.
        timeout: Request timeout in seconds.

    Returns:
        LinkResult describing the outcome.
    """
    try:
        resp = session.head(url, timeout=timeout, allow_redirects=True)
        # Some servers forbid HEAD; retry with GET
        if resp.status_code in (405, 403, 400):
            resp = session.get(url, timeout=timeout, allow_redirects=True, stream=True)
            # Close immediately to avoid downloading the body
            resp.close()

        code = resp.status_code
        final = resp.url if resp.url != url else None

        if 200 <= code < 300:
            category = "ok"
        elif 300 <= code < 400:
            category = "redirect"
        elif 400 <= code < 600:
            category = "dead"
        else:
            category = "error"

        return LinkResult(
            url=url,
            status_code=code,
            category=category,
            final_url=final,
            error_message=None,
            source=source,
        )

    except requests.exceptions.Timeout:
        return LinkResult(
            url=url,
            status_code=None,
            category="timeout",
            final_url=None,
            error_message=f"Timed out after {timeout}s",
            source=source,
        )
    except requests.exceptions.ConnectionError as exc:
        return LinkResult(
            url=url,
            status_code=None,
            category="error",
            final_url=None,
            error_message=str(exc),
            source=source,
        )
    except requests.exceptions.RequestException as exc:
        return LinkResult(
            url=url,
            status_code=None,
            category="error",
            final_url=None,
            error_message=str(exc),
            source=source,
        )


# ---------------------------------------------------------------------------
# Link extraction
# ---------------------------------------------------------------------------

def extract_links_from_markdown(content: str, base_path: str) -> List[Tuple[str, str]]:
    """Extract all links from Markdown content.

    Args:
        content: Raw Markdown text.
        base_path: File path (used as source label).

    Returns:
        List of (url, source) tuples.
    """
    links: List[Tuple[str, str]] = []
    for match in MD_LINK_RE.finditer(content):
        href = match.group(1).split()[0]  # strip optional title
        if href and not href.startswith("#"):
            links.append((href, base_path))
    for match in MD_REF_RE.finditer(content):
        href = match.group(1)
        if href and not href.startswith("#"):
            links.append((href, base_path))
    return links


def extract_links_from_html(content: str, base_url: str) -> List[Tuple[str, str]]:
    """Extract href and src links from HTML content.

    Args:
        content: Raw HTML text.
        base_url: Page URL (used for resolving relative links and as source label).

    Returns:
        List of (absolute_url, source) tuples.
    """
    links: List[Tuple[str, str]] = []
    for pattern in (HTML_HREF_RE, HTML_SRC_RE):
        for match in pattern.finditer(content):
            href = match.group(1).strip()
            if href and not href.startswith(("#", "javascript:", "mailto:", "tel:")):
                abs_url = urllib.parse.urljoin(base_url, href)
                links.append((abs_url, base_url))
    return links


# ---------------------------------------------------------------------------
# Crawl modes
# ---------------------------------------------------------------------------

def scan_local_files(
    root: str,
    extensions: Tuple[str, ...],
    base_url: Optional[str],
) -> List[Tuple[str, str]]:
    """Recursively scan a local directory for links in Markdown/HTML files.

    Args:
        root: Root directory to scan.
        extensions: File extensions to process (e.g. ('.md', '.html')).
        base_url: Base URL for resolving relative links in HTML files.

    Returns:
        List of (url, source_path) tuples. Only HTTP/HTTPS links are included.
    """
    all_links: List[Tuple[str, str]] = []
    root_path = Path(root)

    for ext in extensions:
        for filepath in root_path.rglob(f"*{ext}"):
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                logger.warning("Cannot read %s: %s", filepath, exc)
                continue

            source = str(filepath)
            if ext in (".md", ".markdown"):
                raw_links = extract_links_from_markdown(content, source)
                # Resolve relative links against base_url if provided, else skip non-http
                for href, src in raw_links:
                    if href.startswith(("http://", "https://")):
                        all_links.append((href, src))
                    elif base_url:
                        all_links.append((urllib.parse.urljoin(base_url, href), src))
            else:
                page_url = base_url or f"file://{filepath}"
                raw_links = extract_links_from_html(content, page_url)
                for href, src in raw_links:
                    if href.startswith(("http://", "https://")):
                        all_links.append((href, src))

    return all_links


def crawl_website(
    start_url: str,
    session: requests.Session,
    timeout: int,
    max_depth: int,
    same_domain_only: bool,
) -> Tuple[List[Tuple[str, str]], List[LinkResult]]:
    """BFS-crawl a website collecting all links.

    Args:
        start_url: URL to start crawling from.
        session: Shared requests Session.
        timeout: Request timeout in seconds.
        max_depth: Maximum crawl depth.
        same_domain_only: If True, only follow links on the same domain.

    Returns:
        Tuple of (external_links_to_check, crawl_results_for_internal_pages).
    """
    parsed_start = urllib.parse.urlparse(start_url)
    base_domain = parsed_start.netloc

    visited: Set[str] = set()
    queue: collections.deque = collections.deque([(start_url, 0)])
    external_links: List[Tuple[str, str]] = []
    crawl_results: List[LinkResult] = []

    while queue:
        url, depth = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        logger.info("Crawling [depth=%d]: %s", depth, url)

        try:
            resp = session.get(url, timeout=timeout, allow_redirects=True)
            code = resp.status_code
            final = resp.url if resp.url != url else None

            if 200 <= code < 300:
                category = "ok"
            elif 300 <= code < 400:
                category = "redirect"
            else:
                category = "dead"
                crawl_results.append(
                    LinkResult(url=url, status_code=code, category=category,
                               final_url=final, error_message=None, source=start_url)
                )
                continue

            crawl_results.append(
                LinkResult(url=url, status_code=code, category=category,
                           final_url=final, error_message=None, source=start_url)
            )

            if depth >= max_depth:
                continue

            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type:
                continue

            links = extract_links_from_html(resp.text, resp.url)
            for href, _ in links:
                parsed = urllib.parse.urlparse(href)
                if not parsed.scheme.startswith("http"):
                    continue
                if href in visited:
                    continue
                if parsed.netloc == base_domain:
                    queue.append((href, depth + 1))
                else:
                    external_links.append((href, url))

        except requests.exceptions.Timeout:
            crawl_results.append(
                LinkResult(url=url, status_code=None, category="timeout",
                           final_url=None,
                           error_message=f"Timed out after {timeout}s",
                           source=start_url)
            )
        except requests.exceptions.RequestException as exc:
            crawl_results.append(
                LinkResult(url=url, status_code=None, category="error",
                           final_url=None, error_message=str(exc),
                           source=start_url)
            )

    return external_links, crawl_results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_report(summary: CheckSummary, verbose: bool) -> None:
    """Print a human-readable report to stdout.

    Args:
        summary: CheckSummary containing all results.
        verbose: If True, include OK results in output.
    """
    categories = {
        "dead": "❌ DEAD",
        "timeout": "⏱  TIMEOUT",
        "error": "⚠  ERROR",
        "redirect": "↪  REDIRECT",
        "ok": "✅ OK",
    }

    for result in summary.results:
        if result.category == "ok" and not verbose:
            continue
        label = categories.get(result.category, result.category.upper())
        code_str = str(result.status_code) if result.status_code else "N/A"
        line = f"[{label}] [{code_str}] {result.url}"
        if result.final_url:
            line += f"\n        → {result.final_url}"
        if result.error_message:
            line += f"\n        Error: {result.error_message}"
        line += f"\n        Source: {result.source}"
        print(line)

    print()
    print("=" * 60)
    print(f"  Total links checked : {summary.total}")
    print(f"  OK (2xx)            : {summary.ok}")
    print(f"  Redirects (3xx)     : {summary.redirects}")
    print(f"  Dead (4xx/5xx)      : {summary.dead}")
    print(f"  Timeouts            : {summary.timeouts}")
    print(f"  Errors              : {summary.errors}")
    print("=" * 60)


def export_report(summary: CheckSummary, output_path: str, fmt: str) -> None:
    """Export results to a file.

    Args:
        summary: CheckSummary containing all results.
        output_path: File path to write the report to.
        fmt: Output format — 'json' or 'csv'.
    """
    if fmt == "json":
        data = [
            {
                "url": r.url,
                "status_code": r.status_code,
                "category": r.category,
                "final_url": r.final_url,
                "error_message": r.error_message,
                "source": r.source,
            }
            for r in summary.results
        ]
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    elif fmt == "csv":
        with open(output_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["url", "status_code", "category", "final_url",
                            "error_message", "source"],
            )
            writer.writeheader()
            for r in summary.results:
                writer.writerow(
                    {
                        "url": r.url,
                        "status_code": r.status_code or "",
                        "category": r.category,
                        "final_url": r.final_url or "",
                        "error_message": r.error_message or "",
                        "source": r.source,
                    }
                )
    logger.info("Report exported to %s", output_path)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Parsed namespace.
    """
    parser = argparse.ArgumentParser(
        description="Broken Link Checker — crawl a website or scan local files for dead links.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check a website
  python link_checker.py --url https://example.com

  # Scan a local Markdown repository
  python link_checker.py --local ./docs

  # Concurrent check with JSON output
  python link_checker.py --url https://example.com --workers 20 --output report.json --format json
""",
    )

    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--url", metavar="URL", help="Start URL for website crawl.")
    source_group.add_argument(
        "--local", metavar="DIR", help="Local directory to scan for Markdown/HTML files."
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        metavar="N",
        help=f"Number of concurrent workers (default: {DEFAULT_WORKERS}).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        metavar="SECS",
        help=f"Request timeout in seconds (default: {DEFAULT_TIMEOUT}).",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=DEFAULT_MAX_DEPTH,
        metavar="N",
        help=f"Maximum crawl depth for website mode (default: {DEFAULT_MAX_DEPTH}).",
    )
    parser.add_argument(
        "--external-only",
        action="store_true",
        help="In website mode, only check external links (skip internal page crawl).",
    )
    parser.add_argument(
        "--base-url",
        metavar="URL",
        help="Base URL for resolving relative links in --local mode.",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Export results to a file.",
    )
    parser.add_argument(
        "--format",
        choices=["json", "csv"],
        default="json",
        help="Export format when --output is specified (default: json).",
    )
    parser.add_argument(
        "--fail-on-dead",
        action="store_true",
        help="Exit with code 1 if any dead links are found.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Also log OK links."
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_checks(
    links_with_sources: List[Tuple[str, str]],
    session: requests.Session,
    timeout: int,
    workers: int,
) -> List[LinkResult]:
    """Concurrently check a list of (url, source) pairs.

    Args:
        links_with_sources: List of (url, source) tuples to check.
        session: Shared requests Session.
        timeout: Request timeout per request.
        workers: Maximum thread-pool size.

    Returns:
        List of LinkResult objects.
    """
    # De-duplicate URLs but track all sources
    url_to_sources: Dict[str, List[str]] = {}
    for url, src in links_with_sources:
        url_to_sources.setdefault(url, []).append(src)

    unique_urls = list(url_to_sources.keys())
    logger.info("Checking %d unique URLs with %d workers…", len(unique_urls), workers)

    results: List[LinkResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_url = {
            executor.submit(check_url, url, url_to_sources[url][0], session, timeout): url
            for url in unique_urls
        }
        for future in concurrent.futures.as_completed(future_to_url):
            result = future.result()
            results.append(result)
            logger.debug("Done: %s → %s", result.url, result.category)

    return results


def build_summary(results: List[LinkResult]) -> CheckSummary:
    """Aggregate individual link results into a CheckSummary.

    Args:
        results: List of LinkResult objects.

    Returns:
        Populated CheckSummary.
    """
    summary = CheckSummary(total=len(results), results=results)
    for r in results:
        if r.category == "ok":
            summary.ok += 1
        elif r.category == "redirect":
            summary.redirects += 1
        elif r.category == "dead":
            summary.dead += 1
        elif r.category == "timeout":
            summary.timeouts += 1
        else:
            summary.errors += 1
    return summary


def main(argv: Optional[List[str]] = None) -> None:
    """Main entry point for link_checker.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).
    """
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    session = build_session(DEFAULT_USER_AGENT, args.timeout)
    start_time = time.monotonic()

    links_to_check: List[Tuple[str, str]] = []
    crawl_results: List[LinkResult] = []

    if args.url:
        if args.external_only:
            external, crawl_results = crawl_website(
                args.url, session, args.timeout, args.max_depth, same_domain_only=True
            )
            links_to_check = external
        else:
            external, crawl_results = crawl_website(
                args.url, session, args.timeout, args.max_depth, same_domain_only=False
            )
            links_to_check = external
    else:
        # Local directory scan
        local_path = args.local
        if not os.path.isdir(local_path):
            logger.error("'%s' is not a valid directory.", local_path)
            sys.exit(1)
        links_to_check = scan_local_files(
            local_path, (".md", ".markdown", ".html", ".htm"), args.base_url
        )

    # Run concurrent checks
    check_results = run_checks(links_to_check, session, args.timeout, args.workers)
    all_results = crawl_results + check_results

    summary = build_summary(all_results)
    elapsed = time.monotonic() - start_time

    print_report(summary, args.verbose)
    print(f"  Completed in        : {elapsed:.1f}s")

    if args.output:
        export_report(summary, args.output, args.format)

    if args.fail_on_dead and (summary.dead > 0 or summary.timeouts > 0 or summary.errors > 0):
        sys.exit(1)


if __name__ == "__main__":
    main()
