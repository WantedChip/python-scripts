# Bulk File Renamer with Undo

A safe, transactional bulk file renaming CLI tool written using only the Python standard library. It supports pipeline transformations, pre-flight collision checks, 2-phase rename execution (to handle swap/chains), and rollback/undo functionality.

## Features

- **Sequential Pipeline**: Applies modifications in the following order:
  1. **Casing & Spaces**: Lowercase/uppercase stem, replace spaces with a custom character.
  2. **Date Cleanup**: Standardize ambiguous dates (e.g., `DD-MM-YYYY`, `MM-DD-YYYY`) to `YYYY-MM-DD` based on specified rules.
  3. **Regex Search & Replace**: Find regex patterns and replace them, supporting capture group backreferences (e.g. `\1`).
  4. **Numbering & Sorting**: Append/insert zero-padded numbers based on files sorted by name, size, or modification time.
- **Transactional Validation**: Pre-flight checks to prevent many-to-one collisions and overwriting external files on disk.
- **2-Phase Renaming**: Renames files to unique temporary names before moving them to final targets. Safely handles circular swaps (e.g. `a.txt <-> b.txt`) and renaming chains (e.g. `a.txt -> b.txt -> c.txt`).
- **Undo / Rollback Capability**: Records a portable JSON log of all renames. Reverts them back to original states in reverse order with partial-undo safety.

## Command-Line Interface

### Arguments

| Argument | Description | Default |
|---|---|---|
| `-d`, `--dir` | Target directory to process | `.` |
| `--match` | Glob pattern to match files | `*` |
| `--exclude` | Glob pattern to exclude files | `None` |
| `-r`, `--recursive` | Scan subdirectories recursively | `False` |
| `--regex-find` | Regex pattern to search for in stem | `None` |
| `--regex-replace` | Replacement string (supports `\1` backreferences) | `""` |
| `--number` | Enable sequential numbering | `False` |
| `--number-start` | Start value for sequential numbering | `1` |
| `--number-step` | Increment step for numbering | `1` |
| `--number-padding` | Padding width for sequential numbering | `3` |
| `--number-format` | Format string (placeholders: `{name}`, `{num}`) | `{name}_{num}` |
| `--sort` | Sorting method (`name`, `mtime`, `size`) before numbering | `name` |
| `--clean-dates` | Enable date cleanup / normalization to `YYYY-MM-DD` | `False` |
| `--date-format` | Format to resolve ambiguous date inputs (`DMY`, `MDY`, `YMD`) | `YMD` |
| `--lower` | Convert filename stem to lowercase | `False` |
| `--upper` | Convert filename stem to uppercase | `False` |
| `--replace-spaces` | Replace spaces with optional character (defaults to `_` if flag only) | `None` |
| `--dry-run` | Preview proposed changes and exit | `False` |
| `--force` | Skip confirmation prompts before renaming | `False` |
| `--history-file` | Path to history log file | `.rename_history.json` |
| `--undo` | Rollback the last rename operation using the history file | `False` |

---

## Usage Examples

### 1. Dry Run / Preview Changes
Preview what would be renamed without modifying files:
```bash
python file_renamer.py -d ./data --lower --replace-spaces --dry-run
```

### 2. Standardizing Dates & Lowercasing
Convert filenames containing arbitrary dates to use normalized ISO dates, lowercase them, and replace spaces with underscores:
```bash
python file_renamer.py -d ./data --clean-dates --date-format DMY --lower --replace-spaces
```
*Example*: `My Invoice 12-05-2023.PDF` becomes `my_invoice_2023-05-12.pdf`.

### 3. Regex Replace with Backreferences
Swap prefix and suffix separated by a dash:
```bash
python file_renamer.py -d ./data --regex-find "([a-z]+)-(\d+)" --regex-replace "\2-\1"
```
*Example*: `report-2024.txt` becomes `2024-report.txt`.

### 4. Sequential Numbering
Sort files by size and add padded numbers at the front:
```bash
python file_renamer.py -d ./data --number --number-format "{num}_{name}" --number-start 10 --number-padding 4 --sort size
```
*Example*: `image.png` (smallest) becomes `0010_image.png`.

### 5. Undo / Rollback
Revert the last renaming operation performed in `./data`:
```bash
python file_renamer.py -d ./data --undo
```

---

## Transaction Safety and Rollback Behavior

### 2-Phase Execution
To prevent conflicts like circular swaps (`a.txt -> b.txt` and `b.txt -> a.txt`) or chains (`a.txt -> b.txt -> c.txt`), the program renames files in two distinct phases:
1. **Phase 1 (Temp Renaming)**: Moves all target files to unique temporary filenames in their respective directories (e.g. `<filename>.<uuid>.tmp_rename`). If any rename fails during this phase, the tool immediately reverts all successfully completed temporary renames and aborts.
2. **Phase 2 (Final Renaming)**: Moves the temporary files to their final destination paths. If this phase fails midway, the tool rolls back already completed moves and restores all files to their original names.

### Rollback / Undo
- Running the tool creates a `.rename_history.json` log in the target directory (or a custom path via `--history-file`).
- This log records relative paths, ensuring portability if the target directory is moved or renamed.
- When `--undo` is triggered:
  1. The log is parsed, and original vs target paths are resolved.
  2. A pre-flight validation ensures all renamed files still exist on disk and no new files occupy the original paths (unless part of the undo plan).
  3. The files are renamed back to their original names in **reverse order** using the same 2-phase transactional renaming logic.
  4. On success, the log is renamed to `.rename_history.json.undone` (or deleted).
  5. If an undo fails midway, the remaining uncompleted operations are written back to the history file. This provides **partial undo safety**, letting you rerun the `--undo` command later to finish rolling back.

Quality: pylint 10.00/10 · 84% coverage · 0 dependencies
