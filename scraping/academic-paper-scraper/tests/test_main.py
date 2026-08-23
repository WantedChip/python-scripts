"""Unit tests for Academic Paper Scraper."""

import contextlib
import io
import json
import os
import tempfile
import unittest
import urllib.error
from typing import Any, List
from unittest.mock import MagicMock, patch

from main import (
    ArxivPaper,
    build_arxiv_query,
    build_parser,
    download_paper_pdf,
    fetch_arxiv_papers,
    main,
    paper_to_bibtex,
    papers_to_markdown,
    parse_arxiv_atom_xml,
)


def _urlopen_result(payload: Any, status: int = 200) -> MagicMock:
    """Build a mock urlopen return value usable as a context manager."""
    resp = MagicMock()
    resp.status = status
    body = payload if isinstance(payload, str) else json.dumps(payload)
    resp.read.return_value = body.encode("utf-8")
    resp.__enter__.return_value = resp
    return resp


def _urlopen_bytes(data: bytes, status: int = 200) -> MagicMock:
    """Build a mock urlopen context manager serving raw binary bytes."""
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = data
    resp.__enter__.return_value = resp
    return resp


ATOM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <title>  Sparse   Attention
            Revisited </title>
    <summary> A study of sparse attention patterns. </summary>
    <published>2024-01-20T09:00:00Z</published>
    <updated>2024-02-01T09:00:00Z</updated>
    <author><name>Grace Hopper</name></author>
    <author><name>Alan Turing</name></author>
    <arxiv:primary_category term="cs.LG"/>
    <category term="cs.LG"/>
    <category term="stat.ML"/>
    <link href="http://arxiv.org/abs/2401.12345v1" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2401.12345v1"
          rel="related" type="application/pdf"/>
    <arxiv:journal_ref>Nature ML 12(3), 2024</arxiv:journal_ref>
    <arxiv:doi>10.1000/example.doi</arxiv:doi>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2402.99999v2</id>
    <title>Minimal Entry Without Links</title>
    <summary>Bare entry used to exercise fallbacks.</summary>
    <published>2024-02-05T10:00:00Z</published>
    <updated>2024-02-05T10:00:00Z</updated>
    <category term="cs.AI"/>
  </entry>
</feed>
"""


def _make_paper(**overrides: Any) -> ArxivPaper:
    """Create a fully-populated ArxivPaper with optional field overrides."""
    fields = dict(
        arxiv_id="1706.03762",
        title="Attention Is All You Need",
        authors=["Ashish Vaswani"],
        summary="Transformer architecture paper",
        published="2017-06-12",
        updated="2017-06-12",
        primary_category="cs.CL",
        categories=["cs.CL"],
        pdf_url="https://arxiv.org/pdf/1706.03762.pdf",
        entry_url="https://arxiv.org/abs/1706.03762",
    )
    fields.update(overrides)
    return ArxivPaper(**fields)


class TestAcademicPaperScraper(unittest.TestCase):
    """Test suite for arXiv query building, XML parsing, and BibTeX generation."""

    def test_build_arxiv_query(self) -> None:
        self.assertEqual(
            build_arxiv_query(search_term="deep learning"),
            "all:deep learning",
        )
        self.assertEqual(build_arxiv_query(category="cs.AI"), "cat:cs.AI")
        self.assertEqual(
            build_arxiv_query(search_term="transformer", category="cs.CL"),
            "all:transformer AND cat:cs.CL",
        )

    def test_parse_arxiv_atom_xml(self) -> None:
        atom_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom"
              xmlns:arxiv="http://arxiv.org/schemas/atom">
            <entry>
                <id>http://arxiv.org/abs/1706.03762v7</id>
                <title> Attention Is All You Need </title>
                <summary> We propose the Transformer model... </summary>
                <published>2017-06-12T17:57:34Z</published>
                <updated>2023-08-02T16:00:00Z</updated>
                <author><name>Ashish Vaswani</name></author>
                <author><name>Noam Shazeer</name></author>
                <arxiv:primary_category term="cs.CL"/>
                <category term="cs.CL"/>
                <link href="http://arxiv.org/abs/1706.03762v7"
                      rel="alternate" type="text/html"/>
                <link title="pdf" href="http://arxiv.org/pdf/1706.03762v7"
                      rel="related" type="application/pdf"/>
            </entry>
        </feed>
        """
        papers = parse_arxiv_atom_xml(atom_xml)
        self.assertEqual(len(papers), 1)
        paper = papers[0]
        self.assertEqual(paper.arxiv_id, "1706.03762v7")
        self.assertEqual(paper.title, "Attention Is All You Need")
        self.assertEqual(paper.authors, ["Ashish Vaswani", "Noam Shazeer"])
        self.assertEqual(paper.primary_category, "cs.CL")
        self.assertEqual(paper.pdf_url, "http://arxiv.org/pdf/1706.03762v7")

    def test_paper_to_bibtex(self) -> None:
        title = (
            "Learning Transferable Visual Models From " "Natural Language Supervision"
        )
        paper = ArxivPaper(
            arxiv_id="2103.00020",
            title=title,
            authors=["Alec Radford", "Jong Wook Kim"],
            summary="Test abstract",
            published="2021-03-01T00:00:00Z",
            updated="2021-03-01T00:00:00Z",
            primary_category="cs.CV",
            categories=["cs.CV"],
            pdf_url="https://arxiv.org/pdf/2103.00020.pdf",
            entry_url="https://arxiv.org/abs/2103.00020",
        )
        bib = paper_to_bibtex(paper)
        self.assertIn("@article{radford2021210300020,", bib)
        self.assertIn("author    = {Alec Radford and Jong Wook Kim},", bib)
        self.assertIn("eprint    = {2103.00020},", bib)

    def test_papers_to_markdown(self) -> None:
        paper = _make_paper()
        md = papers_to_markdown([paper])
        self.assertIn("# arXiv Academic Paper Search Digest", md)
        self.assertIn("## 1. Attention Is All You Need", md)
        self.assertIn("> Transformer architecture paper", md)


class TestAtomParsingDetails(unittest.TestCase):
    """Deeper parsing behavior of parse_arxiv_atom_xml."""

    def test_malformed_xml_returns_empty_list(self) -> None:
        self.assertEqual(parse_arxiv_atom_xml("<feed><broken>"), [])

    def test_whitespace_collapsed_in_title_and_summary(self) -> None:
        papers = parse_arxiv_atom_xml(ATOM_XML)
        self.assertEqual(papers[0].title, "Sparse Attention Revisited")
        self.assertEqual(papers[0].summary, "A study of sparse attention patterns.")

    def test_categories_journal_ref_and_doi_extracted(self) -> None:
        paper = parse_arxiv_atom_xml(ATOM_XML)[0]
        self.assertEqual(paper.categories, ["cs.LG", "stat.ML"])
        self.assertEqual(paper.primary_category, "cs.LG")
        self.assertEqual(paper.journal_ref, "Nature ML 12(3), 2024")
        self.assertEqual(paper.doi, "10.1000/example.doi")

    def test_pdf_url_fallback_when_link_missing(self) -> None:
        """Entries without a PDF link synthesize one from the arXiv id."""
        paper = parse_arxiv_atom_xml(ATOM_XML)[1]
        self.assertEqual(paper.pdf_url, "https://arxiv.org/pdf/2402.99999v2.pdf")
        self.assertEqual(paper.entry_url, "http://arxiv.org/abs/2402.99999v2")

    def test_primary_category_defaults_from_plain_categories(self) -> None:
        paper = parse_arxiv_atom_xml(ATOM_XML)[1]
        self.assertEqual(paper.primary_category, "cs.AI")


class TestFetchAndDownload(unittest.TestCase):
    """HTTP layer with mocked urlopen."""

    def test_fetch_arxiv_papers_success(self) -> None:
        with patch(
            "main.urllib.request.urlopen", return_value=_urlopen_result(ATOM_XML)
        ) as mock_open:
            papers = fetch_arxiv_papers("all:attention", max_results=5)
        self.assertEqual(len(papers), 2)
        url = mock_open.call_args.args[0].full_url
        self.assertIn("max_results=5", url)

    def test_fetch_arxiv_papers_non_200_returns_empty(self) -> None:
        resp = _urlopen_result(ATOM_XML, status=503)
        with patch("main.urllib.request.urlopen", return_value=resp):
            self.assertEqual(fetch_arxiv_papers("all:anything"), [])

    def test_fetch_arxiv_papers_network_error_returns_empty(self) -> None:
        with patch(
            "main.urllib.request.urlopen",
            side_effect=urllib.error.URLError("offline"),
        ):
            self.assertEqual(fetch_arxiv_papers("all:anything"), [])

    def test_download_paper_pdf_success_writes_bytes(self) -> None:
        payload = b"%PDF-1.4 fake bytes"
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = os.path.join(tmpdir, "paper.pdf")
            resp = _urlopen_bytes(payload)
            with patch("main.urllib.request.urlopen", return_value=resp):
                ok = download_paper_pdf("https://arxiv.org/pdf/x.pdf", dest)
            self.assertTrue(ok)
            with open(dest, "rb") as f:
                self.assertEqual(f.read(), payload)

    def test_download_paper_pdf_failure_returns_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = os.path.join(tmpdir, "paper.pdf")
            with patch(
                "main.urllib.request.urlopen",
                side_effect=urllib.error.URLError("refused"),
            ):
                self.assertFalse(download_paper_pdf("https://arxiv.org/x", dest))


class TestBibtexAndMarkdownFormatting(unittest.TestCase):
    """Formatting edge cases."""

    def test_bibtex_without_authors_uses_unknown_surname(self) -> None:
        bib = paper_to_bibtex(_make_paper(authors=[]))
        self.assertIn("@article{unknown2017170603762,", bib)
        self.assertIn("author    = {},", bib)

    def test_bibtex_short_published_date_defaults_year(self) -> None:
        bib = paper_to_bibtex(_make_paper(arxiv_id="abc-def", published=""))
        self.assertIn("@article{vaswani2026abcdef,", bib)

    def test_markdown_empty_list_still_has_header(self) -> None:
        md = papers_to_markdown([])
        self.assertIn("Total Papers Found: 0", md)

    def test_markdown_shows_links_and_metadata(self) -> None:
        md = papers_to_markdown([_make_paper()])
        self.assertIn("**Authors:** Ashish Vaswani", md)
        self.assertIn("[Abstract](https://arxiv.org/abs/1706.03762)", md)
        self.assertIn("[PDF](https://arxiv.org/pdf/1706.03762.pdf)", md)
        self.assertIn("**Published:** 2017-06-12", md)


class TestAcademicCli(unittest.TestCase):
    """CLI-level tests for build_parser and main()."""

    def test_build_parser_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        self.assertIsNone(args.query)
        self.assertIsNone(args.category)
        self.assertEqual(args.max_results, 10)
        self.assertEqual(args.format, "markdown")
        self.assertEqual(args.output_dir, "pdf_downloads")
        self.assertFalse(args.download_pdf)

    def _run_main_capture(self, argv: List[str]) -> tuple:
        """Run main() capturing stdout; returns (exit_code, stdout_text)."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue()

    def test_main_no_results_returns_error(self) -> None:
        err = io.StringIO()
        with patch("main.fetch_arxiv_papers", return_value=[]):
            with contextlib.redirect_stderr(err):
                code = main(["--query", "nothing matches"])
        self.assertEqual(code, 1)
        self.assertIn("No papers found matching the query criteria.", err.getvalue())

    def test_main_markdown_stdout_and_json_file_output(self) -> None:
        papers = [_make_paper()]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "digest.json")
            with patch("main.fetch_arxiv_papers", return_value=papers):
                code, out = self._run_main_capture(
                    ["--query", "attention", "--format", "json", "-o", out_path]
                )
            self.assertEqual(code, 0)
            self.assertIn(f"Paper digest saved to {out_path}", out)
            with open(out_path, encoding="utf-8") as f:
                saved: Any = json.load(f)
            self.assertEqual(saved[0]["arxiv_id"], "1706.03762")

    def test_main_bibtex_format_prints_entries(self) -> None:
        with patch("main.fetch_arxiv_papers", return_value=[_make_paper()]):
            code, out = self._run_main_capture(
                ["--query", "attention", "--format", "bibtex"]
            )
        self.assertEqual(code, 0)
        self.assertIn("@article{vaswani2017170603762,", out)

    def test_main_download_pdf_invokes_downloader_per_paper(self) -> None:
        papers = [_make_paper(), _make_paper(arxiv_id="1801.00001")]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "digest.md")
            dl_dir = os.path.join(tmpdir, "pdfs")
            with patch("main.fetch_arxiv_papers", return_value=papers):
                with patch("main.download_paper_pdf", return_value=True) as mock_dl:
                    code, out = self._run_main_capture(
                        [
                            "--query",
                            "attention",
                            "-o",
                            out_path,
                            "--download-pdf",
                            "--output-dir",
                            dl_dir,
                        ]
                    )
            self.assertEqual(code, 0)
            self.assertIn("Downloading 2 PDFs", out)
            self.assertEqual(mock_dl.call_count, 2)
            first_dest = mock_dl.call_args_list[0].args[1]
            self.assertTrue(first_dest.endswith(os.path.join(dl_dir, "1706_03762.pdf")))


if __name__ == "__main__":
    unittest.main()
