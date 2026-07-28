# pdf-form-filler

Fills PDF interactive form fields programmatically using a JSON data file.

## Usage

### Dump Form Fields to Console
```bash
python tools/pdf-form-filler/pdf_form_filler.py form.pdf --dump-fields
```

### Fill Form Fields from JSON File
```bash
python tools/pdf-form-filler/pdf_form_filler.py form.pdf -d field_values.json -o output_filled.pdf
```

## Options
- `-d`, `--data`: Path to JSON file mapping field names to value strings.
- `-o`, `--output`: Destination filled output PDF path.
- `--dump-fields`: Dump interactive form field names and exit.
- `-p`, `--password`: Password for encrypted PDF.
- `-v`, `--verbose`: Enable debug logging.

## Requirements
- `pypdf==6.12.1`

## Quality
Quality: pylint 10.00/10 · 86% coverage · 1 dependency
