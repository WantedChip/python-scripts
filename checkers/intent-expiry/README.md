# Intent Expiry Checker

Audit `TODO`, `FIXME`, and `HACK` comments in codebases against Git history and referenced symbols to determine if their original intent has expired or been completed.

## Features
- Extracts `TODO`, `FIXME`, and `HACK` comments across repository files.
- Retrieves Git blame author, commit, and date information.
- Checks if referenced symbols/functions exist in the codebase.
- Classifies comments into `Active`, `Completed`, or `Obsolete`.

## Usage

```bash
python main.py --path /path/to/codebase
```
