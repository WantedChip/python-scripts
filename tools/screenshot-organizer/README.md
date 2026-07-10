# CLI Screenshot Organizer

A powerful CLI tool to automatically sort and organize screenshots by date, OCR text, application/window clues, and perceptual duplicate similarity.

## Features

- **Date Sorting:** Categorizes screenshots based on dates parsed from EXIF tags, common screenshot filename patterns (Windows/macOS/Linux), or file modification/creation times.
- **Application Detection:** Resolves the source application from filename markers (e.g. `Screenshot - Chrome.png`) and falls back to OCR content scanning.
- **OCR Keyword Scanning:** Scans text in screenshots to associate them with a configurable set of popular apps or custom keyword mappings.
- **Duplicate Cluster Quarantining:** Uses a fast Difference Hashing (dHash) algorithm to detect identical or slightly altered duplicates, quarantining them with their metadata inside a `duplicates/` directory.
- **Dry Run Mode:** Preview file sorting structures and potential duplicates without making any permanent filesystem changes.

## Prerequisites & Installation

### Python Dependencies
Install the required packages in your environment:
```bash
pip install -r requirements.txt
```

### OCR Setup (Optional)
To enable text scanning and app resolution from OCR content, the system requires the **Tesseract OCR** binary:
- **Windows:** Install via Chocolatey: `choco install tesseract` or download installers from [UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki).
- **macOS:** Install via Homebrew: `brew install tesseract`.
- **Linux:** Install via apt: `sudo apt-get install tesseract-ocr`.

*Note: If Tesseract is not installed or configured in your system `PATH`, the script will gracefully fallback to date, filename, and similarity-based organization, skipping the OCR stages.*

## Usage

```bash
python -m screenshot_organizer.main <source_dir> <dest_dir> [options]
```

### Arguments & Options
- `source_dir`: Path to the folder containing screenshots to organize.
- `dest_dir`: Path to the destination root folder.
- `--action {move,copy}`: File operation to perform (default: `move`).
- `--by <criteria>`: Comma-separated sorting hierarchy, e.g. `date,app,duplicate` (default: `date,app,duplicate`).
- `--date-format {YYYY-MM-DD,YYYY-MM,YYYY/MM}`: Format of date directories.
- `--no-ocr`: Disable OCR-based app categorization entirely.
- `--ocr-lang <lang>`: Tesseract OCR language code (default: `eng`).
- `--app-keywords <config>`: Map keywords to application folders. Can be a path to a JSON file or a raw key-val string (e.g., `Chrome=chrome,Discord=discord`).
- `--similarity-threshold <dist>`: Hamming distance similarity threshold (0-64, default: `4`).
- `--dry-run`: Performs a dry run preview.
- `-v, --verbose`: Enable debug logging.

### Examples

#### Basic Move & Sort by Date + App
```bash
python -m screenshot_organizer.main ~/Desktop/screenshots ~/OrganizedScreenshots
```

#### Copy, Sort by App first, then Date, and Disable OCR
```bash
python -m screenshot_organizer.main ~/Desktop/screenshots ~/Organized --action copy --by app,date --no-ocr
```

#### Custom App Keyword Mapping (JSON config)
Create `apps.json`:
```json
{
  "Design": ["figma", "photoshop", "illustrator"],
  "Coding": ["vscode", "github", "stack overflow"]
}
```
Run the organizer:
```bash
python -m screenshot_organizer.main ~/Desktop/screenshots ~/Organized --app-keywords apps.json
```

## Running Tests
Run the unit test suite to verify code correctness and coverage:
```bash
$env:PYTHONPATH="src"; pytest tests/ --cov=src/ --cov-report=term-missing
```
