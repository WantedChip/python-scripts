# Documentation Site Scraper

Crawls documentation site pages from a sitemap or root URL and compiles them into a single-page offline HTML or Markdown reference file.

## Features
- **Depth & Domain Restricted Crawler**: Crawls doc links within the base domain while enforcing depth and max-page limits.
- **Clutter-Free Extraction**: Automatically strips navigation headers, sidebars, footers, scripts, and non-content elements (`<nav>`, `<aside>`, `<header>`, `<footer>`).
- **Sitemap Parsing**: Optionally parses `sitemap.xml` to locate all documentation pages efficiently.
- **Single-Page Reference Builder**: Generates structured HTML/Markdown with interactive/anchored Table of Contents.

## Usage

```bash
# Crawl root URL and generate single-page HTML offline reference
python main.py --root-url https://docs.example.com --max-depth 2 --max-pages 15 --output-file offline_docs.html

# Crawl from sitemap XML and output single Markdown file
python main.py --root-url https://docs.example.com --sitemap https://docs.example.com/sitemap.xml --output-format md --output-file offline_docs.md
```

## Running Tests

```bash
python -m unittest discover tests
```
