"""Unit tests for Academic Paper Scraper."""

import unittest

from main import (
    ArxivPaper,
    build_arxiv_query,
    paper_to_bibtex,
    papers_to_markdown,
    parse_arxiv_atom_xml,
)


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
        paper = ArxivPaper(
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
        md = papers_to_markdown([paper])
        self.assertIn("# arXiv Academic Paper Search Digest", md)
        self.assertIn("## 1. Attention Is All You Need", md)
        self.assertIn("> Transformer architecture paper", md)


if __name__ == "__main__":
    unittest.main()
