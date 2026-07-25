# Hotfix Debt Checker

Find production hotfixes in deployed files or server copies that were never committed back to git source control.

## Features
- Compares a deployed directory against checked-in source code.
- Ignores deployment artifacts, logs, temporary files, and `.git` folders.
- Flags uncommitted manual production changes (`MODIFIED`, `DEPLOYED_ONLY`, `MISSING_IN_DEPLOYMENT`).
- Generates a candidate patch file (`hotfix-debt patch`) to merge hotfixes back into source control.

## Usage

### Scan for hotfixes
```bash
python main.py scan --repo /path/to/git/repo --deployed /path/to/deployed/server
```

### Generate a candidate patch file
```bash
python main.py patch --repo /path/to/git/repo --deployed /path/to/deployed/server --output production-hotfix.patch
```
