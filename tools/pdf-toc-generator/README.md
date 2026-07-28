# pdf-toc-generator

Generates interactive outline bookmarks (table of contents) for a PDF based on heading text analysis or JSON outline.

## Usage

### Auto-Detect Headings and Add TOC
```bash
python tools/pdf-toc-generator/pdf_toc_generator.py document.pdf -o output_toc.pdf
```

### Use JSON Configuration Outline
```bash
python tools/pdf-toc-generator/pdf_toc_generator.py document.pdf -c outline.json -o output_toc.pdf
```

## Options
- `-c`, `--config`: Path to JSON file defining outline entries `[{"title": "Intro", "page": 1}]`.
- `--pattern`: Custom regex pattern for heading detection.
- `-o`, `--output`: Destination modified PDF output path.
- `-p`, `--password`: Password for encrypted PDF.
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `pypdf==6.12.1`

## Quality
Quality: pylint 10.00/10 · 84% coverage · 1 dependency
