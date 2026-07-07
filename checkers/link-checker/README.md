# Broken Link Checker

Crawls a website or scans a local Markdown/HTML repository and reports dead links, redirects, and timeouts.

## Features

- **Website crawl mode**: BFS crawl starting from a URL up to a configurable depth.
- **Local scan mode**: Recursively scan `.md`, `.html` files for external links.
- **Concurrent checking**: Thread-pool for fast parallel HTTP checks.
- **HEAD → GET fallback**: Falls back to GET when servers reject HEAD requests.
- **Categories**: `ok` (2xx), `redirect` (3xx), `dead` (4xx/5xx), `timeout`, `error`.
- **Export**: Save results as JSON or CSV with `--output`.

## Requirements

```
pip install -r requirements.txt
```

Requires Python 3.9+.

## Usage

```bash
# Check a website
python link_checker.py --url https://example.com

# Scan local Markdown files
python link_checker.py --local ./docs

# Increase concurrency and set a custom timeout
python link_checker.py --url https://example.com --workers 20 --timeout 15

# Export JSON report
python link_checker.py --local ./docs --output report.json --format json

# Export CSV report
python link_checker.py --url https://example.com --output report.csv --format csv

# Exit with code 1 if dead links are found (useful in CI)
python link_checker.py --local ./docs --fail-on-dead

# Show all links including OK ones
python link_checker.py --url https://example.com -v
```

## Options

| Argument | Description | Default |
|---|---|---|
| `--url URL` | Start URL for website crawl | — |
| `--local DIR` | Directory to scan for Markdown/HTML files | — |
| `--workers N` | Number of concurrent request workers | 10 |
| `--timeout SECS` | Request timeout in seconds | 10 |
| `--max-depth N` | Crawl depth limit (website mode) | 3 |
| `--external-only` | Only check external links (skip internal crawl) | False |
| `--base-url URL` | Base URL for relative links in local mode | None |
| `--output FILE` | Save report to file | None |
| `--format` | Report format: `json` or `csv` | json |
| `--fail-on-dead` | Exit code 1 if any dead/timeout/error links | False |
| `-v, --verbose` | Also show OK links in console output | False |

## Notes

- `--url` and `--local` are mutually exclusive; exactly one is required.
- Internal pages are crawled with the BFS crawler; external links on those pages are checked concurrently via the thread pool.
- The tool sends a `User-Agent: LinkChecker/1.0` header; some servers may still block requests.

## Running Tests

```bash
pytest
```
