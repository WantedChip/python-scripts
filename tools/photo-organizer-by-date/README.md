# Photo Organizer by Date

Organize image files into structured folders (`YYYY/MM` or `YYYY-MM-DD`) based on EXIF metadata (`DateTimeOriginal`) or file modification dates.

## Features

- **EXIF Date Extraction**: Reads EXIF `DateTimeOriginal` / `DateTime` metadata from images (supports Pillow or built-in pure-Python JPEG parser).
- **Fallback Mechanism**: Gracefully falls back to file modification time (`mtime`) if EXIF header is missing or corrupted.
- **Custom Folder Formatting**: Supports `YYYY/MM`, `YYYY-MM-DD`, `YYYY/MM/DD`, or custom datetime formats.
- **Copy or Move Modes**: Choose whether to copy photos or move them.
- **Duplicate Prevention**: Handles naming collisions and prevents duplicate file transfers using file hash comparisons.
- **Dry-run Mode**: Preview target paths before executing file operations.

## Usage

```bash
python main.py --source /path/to/photos --dest /path/to/organized --format YYYY/MM --mode copy --dry-run
```

### Options

- `--source`, `-s`: Source directory containing photos.
- `--dest`, `-d`: Target organized directory.
- `--format`, `-f`: Subfolder format (`YYYY/MM`, `YYYY-MM-DD`, `YYYY/MM/DD`, default: `YYYY/MM`).
- `--mode`, `-m`: File operation mode (`copy` or `move`, default: `copy`).
- `--collision-action`: Handling existing files (`skip`, `rename`, `overwrite`, default: `rename`).
- `--dry-run`: Preview destination without copying/moving files.

## Running Tests

```bash
python -m unittest discover tests
```
