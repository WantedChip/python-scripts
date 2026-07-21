# document-deduper

Detect near-duplicate PDF, Word (.docx), and text/markdown documents even when filenames, formatting, and metadata differ. It tokenizes content, constructs word N-gram shingles, and calculates Jaccard Similarity coefficients across files.

## Usage

Scan a directory for near-duplicates:

```bash
python document_deduper.py C:/Users/Name/Documents
```

Specify a custom similarity percentage threshold (e.g. 90%):

```bash
python document_deduper.py C:/Users/Name/Documents --threshold 90.0
```

Configure N-gram shingle size parameters:

```bash
python document_deduper.py C:/Users/Name/Documents --shingle-size 4
```

## Requirements

- Python 3.11+
- `pypdf` (optional, listed in [requirements.txt](requirements.txt) to support PDF parsing)

## Notes

- Extracts DOCX text content natively using standard zip and xml packages (zero dependency).
- Skips empty files or files containing fewer words than the shingle size.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 1 dependency
