# Downloads Folder Organizer CLI

An automated file organization CLI tool designed to cleanly sort clutter in Downloads or target folders into categorized subdirectories based on extension rules and MIME types.

## Features

- **Categorized Subfolders**: Automatically categorizes files into `Documents`, `Images`, `Archives`, `Audio`, `Video`, `Code`, and `Others`.
- **MIME Type Fallback**: Uses system MIME type detection when file extensions are uncommon or non-standard.
- **Custom Categorization Rules**: Extend or override categories using a simple custom JSON configuration file.
- **Date-Based Sorting**: Optionally organize files into subfolder structures based on modification dates (e.g. `Documents/2026-07`).
- **Collision Protection**: Automatically resolves naming conflicts by appending numeric suffixes (`_1`, `_2`).
- **Dry-Run & Confirmation**: Preview proposed file transfers before performing any disk operations.
- **Undo Manifest Log**: Record all file movements in a JSON manifest for instantaneous 1-click rollback.

## Usage

```bash
python main.py --dir ~/Downloads --apply
```

### CLI Command Options

| Option | Short | Description | Default |
|---|---|---|---|
| `--dir` | `-d` | Target folder to organize | `.` |
| `--config` | `-c` | Path to custom JSON category rules | None |
| `--by-date` | | Subdivide category folders by file modification date | `False` |
| `--date-format` | | Format specifier for date subfolders | `%Y-%m` |
| `--dry-run` | | Preview moves without shifting files | `False` |
| `--apply` | | Execute the file moves | `False` |
| `--yes` | `-y` | Skip confirmation prompt when applying | `False` |
| `--manifest` | | Path for undo JSON log manifest | `organize_undo.json` |
| `--undo` | | Restore files to original locations | `False` |

## Custom Configuration Example (`custom_rules.json`)

```json
{
  "Spreadsheets": [".xlsx", ".csv", ".ods"],
  "Ebooks": [".epub", ".mobi", ".pdf"],
  "Design": [".psd", ".ai", ".fig"]
}
```

Usage with custom config:
```bash
python main.py -d ~/Downloads --config custom_rules.json --apply
```

## Rollback Command

```bash
python main.py --undo --manifest organize_undo.json
```

## Running Unit Tests

```bash
python -m unittest discover tests
```
