"""Academic Paper Scraper.

Queries arXiv API (export.arxiv.org/api/query) by keyword or category to
retrieve paper metadata, abstracts, and PDF links, formatted into Markdown
summaries, BibTeX citations, and optional PDF file downloads.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-instance-attributes
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET  # nosec B405
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ArxivPaper:
    """Dataclass holding normalized academic paper metadata."""

    arxiv_id: str
    title: str
    authors: List[str]
    summary: str
    published: str
    updated: str
    primary_category: str
    categories: List[str]
    pdf_url: str
    entry_url: str
    journal_ref: str = ""
    doi: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert paper object to dictionary."""
        return asdict(self)


def build_arxiv_query(
    search_term: Optional[str] = None,
    category: Optional[str] = None,
) -> str:
    """Construct search query string for arXiv API.

    Args:
        search_term: Free text or keyword search (searches title & abstract).
        category: arXiv category code (e.g. cs.AI, stat.ML, physics.quant-ph).

    Returns:
        Formatted arXiv search query string.
    """
    parts = []
    if search_term:
        cleaned_term = re.sub(r"[^\w\s\-]", "", search_term)
        parts.append(f"all:{cleaned_term}")
    if category:
        parts.append(f"cat:{category}")

    if not parts:
        return "all:machine learning"
    return " AND ".join(parts)


def parse_arxiv_atom_xml(xml_content: str) -> List[ArxivPaper]:
    """Parse arXiv Atom XML API payload into list of ArxivPaper instances.

    Args:
        xml_content: Raw Atom XML text.

    Returns:
        List of parsed ArxivPaper objects.
    """
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }

    try:
        root = ET.fromstring(xml_content)  # nosec B314
    except ET.ParseError:
        return []

    papers: List[ArxivPaper] = []

    for entry in root.findall("atom:entry", ns):
        id_elem = entry.find("atom:id", ns)
        raw_id = id_elem.text.strip() if id_elem is not None and id_elem.text else ""
        arxiv_id = raw_id.split("/abs/")[-1] if "/abs/" in raw_id else raw_id

        title_elem = entry.find("atom:title", ns)
        title = (
            " ".join(title_elem.text.split())
            if title_elem is not None and title_elem.text
            else "Untitled"
        )

        summary_elem = entry.find("atom:summary", ns)
        summary = (
            " ".join(summary_elem.text.split())
            if summary_elem is not None and summary_elem.text
            else ""
        )

        published_elem = entry.find("atom:published", ns)
        published = (
            published_elem.text.strip()
            if published_elem is not None and published_elem.text
            else ""
        )

        updated_elem = entry.find("atom:updated", ns)
        updated = (
            updated_elem.text.strip()
            if updated_elem is not None and updated_elem.text
            else ""
        )

        authors = []
        for author_elem in entry.findall("atom:author", ns):
            name_elem = author_elem.find("atom:name", ns)
            if name_elem is not None and name_elem.text:
                authors.append(name_elem.text.strip())

        categories = []
        primary_cat = ""
        primary_elem = entry.find("arxiv:primary_category", ns)
        if primary_elem is not None:
            primary_cat = primary_elem.attrib.get("term", "")

        for cat_elem in entry.findall("atom:category", ns):
            term = cat_elem.attrib.get("term")
            if term:
                categories.append(term)
                if not primary_cat:
                    primary_cat = term

        pdf_url = ""
        entry_url = raw_id
        for link in entry.findall("atom:link", ns):
            rel = link.attrib.get("rel")
            title_attr = link.attrib.get("title")
            href = link.attrib.get("href", "")
            if title_attr == "pdf" or (rel == "related" and href.endswith(".pdf")):
                pdf_url = href
            elif rel == "alternate":
                entry_url = href

        if not pdf_url and arxiv_id:
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

        journal_elem = entry.find("arxiv:journal_ref", ns)
        journal_ref = (
            journal_elem.text.strip()
            if journal_elem is not None and journal_elem.text
            else ""
        )

        doi_elem = entry.find("arxiv:doi", ns)
        doi = doi_elem.text.strip() if doi_elem is not None and doi_elem.text else ""

        papers.append(
            ArxivPaper(
                arxiv_id=arxiv_id,
                title=title,
                authors=authors,
                summary=summary,
                published=published,
                updated=updated,
                primary_category=primary_cat,
                categories=categories,
                pdf_url=pdf_url,
                entry_url=entry_url,
                journal_ref=journal_ref,
                doi=doi,
            )
        )

    return papers


def fetch_arxiv_papers(
    query: str, max_results: int = 10, timeout: int = 15
) -> List[ArxivPaper]:
    """Execute search request against arXiv REST API.

    Args:
        query: Formatted arXiv query string.
        max_results: Max entries to fetch.
        timeout: Request timeout seconds.

    Returns:
        List of ArxivPaper objects.
    """
    encoded_q = urllib.parse.quote(query)
    base_url = "http://export.arxiv.org/api/query"
    url = (
        f"{base_url}?search_query={encoded_q}&start=0"
        f"&max_results={max_results}&sortBy=submittedDate"
        "&sortOrder=descending"
    )

    req = urllib.request.Request(
        url, headers={"User-Agent": "AcademicPaperScraper/1.0 (Python)"}
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec B310
            if response.status == 200:
                xml_data = response.read().decode("utf-8")
                return parse_arxiv_atom_xml(xml_data)
    except (urllib.error.URLError, OSError, ValueError):
        return []

    return []


def paper_to_bibtex(paper: ArxivPaper) -> str:
    """Generate BibTeX citation entry for an arXiv paper.

    Args:
        paper: ArxivPaper object.

    Returns:
        BibTeX string entry.
    """
    if paper.authors:
        first_author_surname = paper.authors[0].split()[-1].lower()
    else:
        first_author_surname = "unknown"

    year = paper.published[:4] if len(paper.published) >= 4 else "2026"
    clean_id = re.sub(r"[^\w]", "", paper.arxiv_id)
    cite_key = f"{first_author_surname}{year}{clean_id}"

    authors_str = " and ".join(paper.authors)

    bib = [
        f"@article{{{cite_key},",
        f"  title     = {{{paper.title}}},",
        f"  author    = {{{authors_str}}},",
        f"  journal   = {{arXiv preprint arXiv:{paper.arxiv_id}}},",
        f"  year      = {{{year}}},",
        f"  eprint    = {{{paper.arxiv_id}}},",
        "  archivePrefix = {arXiv},",
        f"  primaryClass  = {{{paper.primary_category}}},",
        f"  url       = {{{paper.entry_url}}}",
        "}",
    ]
    return "\n".join(bib)


def papers_to_markdown(papers: List[ArxivPaper]) -> str:
    """Format paper metadata list into Markdown reference digest.

    Args:
        papers: List of ArxivPaper instances.

    Returns:
        Multi-line Markdown document string.
    """
    lines = [
        "# arXiv Academic Paper Search Digest",
        f"Total Papers Found: {len(papers)}",
        "",
        "---",
        "",
    ]

    for idx, p in enumerate(papers, 1):
        pub_date = p.published[:10] if p.published else "N/A"
        authors_str = ", ".join(p.authors)
        lines.extend(
            [
                f"## {idx}. {p.title}",
                "",
                f"**Authors:** {authors_str}  ",
                (
                    f"**arXiv ID:** `{p.arxiv_id}` | "
                    f"**Category:** `{p.primary_category}` | "
                    f"**Published:** {pub_date}  "
                ),
                f"**Links:** [Abstract]({p.entry_url}) | [PDF]({p.pdf_url})",
                "",
                "### Abstract",
                f"> {p.summary}",
                "",
                "---",
                "",
            ]
        )

    return "\n".join(lines)


def download_paper_pdf(pdf_url: str, output_path: str, timeout: int = 20) -> bool:
    """Download PDF binary from URL and write to file.

    Args:
        pdf_url: Target PDF download URL.
        output_path: File destination path.
        timeout: Timeout seconds.

    Returns:
        True if successfully saved, False otherwise.
    """
    req = urllib.request.Request(
        pdf_url, headers={"User-Agent": "AcademicPaperScraper/1.0 (Python)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec B310
            if response.status == 200:
                with open(output_path, "wb") as f:
                    f.write(response.read())
                return True
    except (urllib.error.URLError, OSError, ValueError):
        return False
    return False


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Search arXiv papers by keyword/category and export summaries."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "--query",
        "-q",
        type=str,
        help="Search query keywords (e.g. 'transformer attention')",
    )
    parser.add_argument(
        "--category",
        "-c",
        type=str,
        help="arXiv category code (e.g. cs.CL, cs.CV, stat.ML)",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=10,
        help="Max papers to retrieve (default: 10)",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "bibtex", "json"],
        default="markdown",
        help="Output summary format (default: markdown)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="File path to save the metadata summary",
    )
    parser.add_argument(
        "--download-pdf",
        action="store_true",
        help="Download PDF files into output directory",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="pdf_downloads",
        help="Directory to save downloaded PDFs",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for Academic Paper Scraper."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    q_str = build_arxiv_query(search_term=parsed.query, category=parsed.category)
    papers = fetch_arxiv_papers(q_str, max_results=parsed.max_results)

    if not papers:
        print("No papers found matching the query criteria.", file=sys.stderr)
        return 1

    if parsed.format == "bibtex":
        output_str = "\n\n".join(paper_to_bibtex(p) for p in papers)
    elif parsed.format == "json":
        output_str = json.dumps([p.to_dict() for p in papers], indent=2)
    else:
        output_str = papers_to_markdown(papers)

    if parsed.output:
        with open(parsed.output, "w", encoding="utf-8") as f:
            f.write(output_str)
        print(f"Paper digest saved to {parsed.output}")
    else:
        print(output_str)

    if parsed.download_pdf:
        os.makedirs(parsed.output_dir, exist_ok=True)
        print(f"\nDownloading {len(papers)} PDFs to '{parsed.output_dir}'...")
        for paper in papers:
            filename = f"{re.sub(r'[^\w\-]', '_', paper.arxiv_id)}.pdf"
            dest = os.path.join(parsed.output_dir, filename)
            success = download_paper_pdf(paper.pdf_url, dest)
            if success:
                print(f"  [+] Saved {filename}")
            else:
                print(f"  [-] Failed to download {paper.arxiv_id}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
