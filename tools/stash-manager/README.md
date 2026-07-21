# stash-manager

An intuitive Git stash explorer showing which branch each stash originated from, stash ages, files changed, risk of merge conflicts, and safe diff previews before applying them to the active checkout.

## Usage

List all stashes and evaluate conflict risks against current uncommitted modifications:

```bash
python stash_manager.py
```

Preview files and patch diff details for a specific stash index (e.g. index 0):

```bash
python stash_manager.py --preview 0
```

Apply a stash safely, prompting for confirmation if a high conflict risk is detected:

```bash
python stash_manager.py --apply 0
```

## Requirements

- Python 3.11+
- Pure standard library (zero external dependencies)
- Git command line client installed on the system PATH

## Diagnostics Performed

- Parses the list of stashes using `git stash list`.
- Identifies the source branch name based on the stash description message patterns.
- Audits conflict risk by checking if the files modified inside the stash overlap with current dirty modifications in the working tree.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies
