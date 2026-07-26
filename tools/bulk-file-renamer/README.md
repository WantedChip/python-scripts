# Bulk File Renamer CLI

A feature-rich command-line interface tool for batch renaming files using regular expressions, string formatting, sequential numbering, case transformation, and collision validation.

## Features

- **Regex Search & Replace**: Match filenames with standard Python regular expressions and use capture groups in replacements.
- **Case Formatting**: Transform filenames to `lower`, `upper`, `title`, `camel`, or `snake` case.
- **Sequential Numbering**: Auto-number matching files with customizable start index, step size, and string formatting (e.g. `{:03d}`).
- **Prefix & Suffix**: Prepend or append text to filename stems easily.
- **Collision Safeguards**: Automatically detects target file conflicts and double-mappings before applying changes.
- **Dry-Run & Confirmation**: Preview renames before executing them to avoid accidental changes.
- **Undo Log / Manifest**: Generate undo JSON manifests allowing full rollback of rename operations.

## Usage

```bash
python main.py --dir /path/to/folder --match "img_(\d+)" --replace "vacation_\1" --apply
```

### Command-Line Arguments

| Argument | Short | Description | Default |
|---|---|---|---|
| `--dir` | `-d` | Target directory to process | `.` |
| `--match` | `-m` | Regex pattern to match filenames | `.*` |
| `--replace` | `-r` | Regex replacement pattern | `\g<0>` |
| `--prefix` | | String to prepend to stem | `""` |
| `--suffix` | | String to append to stem | `""` |
| `--number-start` | | Enable sequential numbering starting at integer | `None` |
| `--number-step` | | Step increment for numbering | `1` |
| `--number-format` | | Format string for sequence number | `{:03d}` |
| `--case` | | Case style (`lower`, `upper`, `title`, `camel`, `snake`) | `None` |
| `--recursive` | `-R` | Recursively process subdirectories | `False` |
| `--dry-run` | | Preview changes without modifying files | `False` |
| `--apply` | | Execute the renames | `False` |
| `--yes` | `-y` | Skip confirmation prompt when applying | `False` |
| `--manifest` | | Path for undo JSON manifest file | `rename_manifest.json` |
| `--undo` | | Rollback renames from manifest | `False` |

## Examples

### 1. Regex Replacement
Rename all `DSC_001.JPG` to `photo_001.jpg`:
```bash
python main.py -d ./photos -m "DSC_(\d+)\.JPG" -r "photo_\1.jpg" --apply
```

### 2. Snake Case and Sequential Numbering
```bash
python main.py -d ./docs --case snake --number-start 1 --number-format "{:02d}" --apply
```

### 3. Rollback Previous Rename
```bash
python main.py --undo --manifest rename_manifest.json
```

## Running Unit Tests

```bash
python -m unittest discover tests
```
