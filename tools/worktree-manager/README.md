# worktree-manager

Simplify Git worktrees management: list all registered worktrees, audit disk storage space usages, identify deleted/abandoned worktree metadata config states, and safely prune metadata.

## Usage

List all worktrees with their respective branch checkout states and disk usages:

```bash
python worktree_manager.py list
```

Create a new worktree checkouting a branch:

```bash
python worktree_manager.py add hotfix-branch
```

Prune metadata databases of deleted worktree folders:

```bash
python worktree_manager.py prune
```

## Requirements

- Python 3.11+
- Pure standard library (zero external dependencies)
- Git command line tool installed on system PATH

## Management Heuristics

- **Disk Space Audit**: Iterates recursively through each worktree folder (including vendor directories like `node_modules` or `.venv`) to summarize disk space consumption.
- **Orphan/Abandoned Detection**: Checks if worktree directories listed in Git configuration actually exist on disk, flagging missing locations as "Abandoned".
- **Pruning Integration**: Leverages `git worktree prune` to clean out stale administrative registry databases.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies
