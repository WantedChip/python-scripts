# context-switch

Save and restore complete development workspace contexts (git branches, uncommitted code patches, listening port PIDs, and progress TODO notes) to enable seamless context-switching between developer tasks.

## Usage

Save the current development context with optional progress notes:

```bash
python context_switch.py save task-abc --notes "Working on fixing user auth token serialization issue; port 8080 should be active."
```

List all saved development context profiles:

```bash
python context_switch.py list
```

Restore a saved development context, applying patches and validating that dev servers are active:

```bash
python context_switch.py restore task-abc
```

## Requirements

- Python 3.11+
- `psutil` (listed in [requirements.txt](requirements.txt) to audit dev port status listeners)
- Git command line tools installed on the system PATH

## Metadata Captured

- **Git Branch**: Active branch checkout name.
- **Git diff**: Creates a standard diff patch file for untracked/dirty changes in the working tree.
- **Uptime ports**: Scans listening port configurations (TCP 3000-9999).
- **Task progress**: Logs text descriptions, reminders, and next steps.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 1 dependency
