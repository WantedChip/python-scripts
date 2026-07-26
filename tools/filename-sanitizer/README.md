# Filename Sanitizer

A bulk utility to sanitize filenames by removing illegal filesystem characters, normalizing unicode diacritics/accents, trimming trailing spaces/dots, and replacing space characters safely.

## Features

- **Unicode Normalization**: Removes diacritics and accents (e.g. `résumé.txt` -> `resume.txt`) using `unicodedata`.
- **OS-Specific Cleaning**: Strips invalid characters for Windows (`<>:"/\|?*`) and POSIX systems, along with Windows reserved names (`CON`, `PRN`, etc.).
- **Space Replacement**: Replace whitespace with underscores `_`, hyphens `-`, or collapse multiple spaces.
- **Lowercase Option**: Optional conversion of filenames to lowercase.
- **Preview & Diff Report**: Displays a diff report showing proposed changes prior to renaming.
- **Safe Rename**: Prevents collisions and accidental overwrites during renaming operations.

## Usage

```bash
python main.py --path /path/to/files --space-replacement "_" --lowercase --dry-run
```

### Options

- `--path`, `-p`: Target directory or file path to sanitize (required).
- `--space-replacement`, `-s`: Replace spaces with `_`, `-`, or `none` (default: `_`).
- `--lowercase`, `-l`: Convert filenames to lowercase.
- `--remove-diacritics`: Strip accents and diacritics (default: Enabled).
- `--recursive`, `-r`: Recursively sanitize files in subdirectories.
- `--dry-run`: Preview proposed filename changes without modifying files.

## Running Tests

```bash
python -m unittest discover tests
```
