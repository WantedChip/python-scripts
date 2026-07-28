# pdf-metadata-editor

Views and edits PDF metadata (title, author, subject, keywords, creator, producer).

## Usage

### View PDF Metadata
```bash
python tools/pdf-metadata-editor/pdf_metadata_editor.py document.pdf
```

### View Metadata in JSON Format
```bash
python tools/pdf-metadata-editor/pdf_metadata_editor.py document.pdf -f json
```

### Edit Metadata Tags
```bash
python tools/pdf-metadata-editor/pdf_metadata_editor.py document.pdf --title "New Title" --author "Jane Doe" -o updated.pdf
```

### Update Metadata In-Place
```bash
python tools/pdf-metadata-editor/pdf_metadata_editor.py document.pdf --title "Final Title" --in-place
```

## Options
- `--title`: Set PDF title metadata.
- `--author`: Set PDF author metadata.
- `--subject`: Set PDF subject metadata.
- `--keywords`: Set PDF keywords metadata.
- `--creator`: Set PDF creator metadata.
- `--producer`: Set PDF producer metadata.
- `-o`, `--output`: Target modified PDF path.
- `--in-place`: Save metadata updates directly to input file.
- `-f`, `--format`: Output format for view mode (`table`, `json`).
- `-p`, `--password`: Password for encrypted PDF.
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `pypdf==6.12.1`

## Quality
Quality: pylint 10.00/10 · 86% coverage · 1 dependency
