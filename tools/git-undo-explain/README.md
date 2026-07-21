# git-undo-explain

An interactive terminal disaster recovery advisor explaining how to undo Git mistakes (wrong branch commits, hard resets, accidental caches, etc.), illustrating visual branch status previews, and optionally executing recovery commands.

## Usage

Start the interactive scenario menu:

```bash
python git_undo_explain.py
```

Run a specific scenario (1-5) directly without menu prompts:

```bash
python git_undo_explain.py --scenario 2
```

Execute recovery commands without confirmations:

```bash
python git_undo_explain.py --scenario 2 --yes
```

## Requirements

- Python 3.11+
- Pure standard library (zero external dependencies)
- Git command line tool installed on system PATH

## Scenarios Supported

1. **Committed to wrong branch**: Moves latest commits to feature backups and resets parent branch.
2. **Soft Undo Commit**: Resets HEAD commit, keeping modifications local in the workspace.
3. **Hard Undo Commit**: Resets HEAD commit, discarding changes permanently.
4. **Accidental Hard Reset**: Scans Git reflog to locate SHA1 pointers and restore commits.
5. **Untrack Committed Secret**: Removes target files from cached Git tracking without deleting them from disk.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies
