# Academic Paper Scraper

Searches arXiv by keyword or subject category code, extracts paper metadata (authors, abstract, publication date, primary subject classification, PDF link), and exports Markdown reference digests, BibTeX citations, or PDF paper downloads.

## Features

- **arXiv API Query Engine**: Constructs queries filtering by subject category (e.g. `cs.AI`, `stat.ML`, `physics.quant-ph`) and search terms.
- **Atom XML Parser**: Parses XML schema into structured `ArxivPaper` objects.
- **BibTeX Generator**: Formats academic citations ready for LaTeX insertion.
- **PDF Downloader**: Optional batch downloader to save PDF files to disk.

## Usage

```bash
# Search by query term and output Markdown summary
python main.py -q "transformer attention" --max-results 5

# Search by category and export BibTeX file
python main.py -c cs.CL -q "LLM" --format bibtex -o references.bib

# Download paper PDFs into a folder
python main.py -q "diffusion models" --max-results 3 --download-pdf --output-dir pdfs/
```

## Running Tests

```bash
python -m unittest discover -s tests
```
