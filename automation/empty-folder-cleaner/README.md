# Empty Folder Cleaner CLI

A recursive command-line tool that performs post-order directory traversal to identify and remove empty directory hierarchies in a single pass.

## Features

- **Multi-Level Pruning**: Bottom-up post-order traversal cleans deeply nested empty folders (e.g. `a/b/c/d`) in one operation.
- **Safety Exclusions**: Skip protected directories like `.git`, `.venv`, `node_modules`, `__pycache__`, or user-defined globs.
- **Hidden & System Junk File Purge**: Optionally treat hidden OS files (`.DS_Store`, `desktop.ini`, `Thumbs.db`) as empty and delete them prior to directory removal.
- **Dry-Run Mode**: Safely preview candidate folders before initiating any disk write/deletion operations.
- **Summary Report**: Detailed deletion summary counting folders purged and junk files cleared.

## Usage

```bash
python main.py --dir /path/to/clean --apply
```

### CLI Command Options

| Option | Short | Description | Default |
|---|---|---|---|
| `--dir` | `-d` | Root directory to scan | `.` |
| `--exclude` | | Folder names/globs to ignore | `.git`, `.venv`, `node_modules`, `__pycache__` |
| `--keep-hidden-files` | | Do not ignore `.DS_Store` / `desktop.ini` | `False` |
| `--delete-junk` | | Delete hidden OS junk files in empty folders | `False` |
| `--dry-run` | | Preview empty folders without deleting | `False` |
| `--apply` | | Execute folder deletion | `False` |
| `--yes` | `-y` | Skip interactive confirmation prompt | `False` |

## Examples

### 1. Preview Empty Folders
```bash
python main.py -d ~/Projects --dry-run
```

### 2. Purge Empty Folders & Hidden OS Junk Files
```bash
python main.py -d ~/Downloads --delete-junk --apply
```

### 3. Exclude Specific Directory Patterns
```bash
python main.py -d ./workspace --exclude build dist "*.tmp" --apply
```

## Running Unit Tests

```bash
python -m unittest discover tests
```
