# Note Taker CLI

A command-line tool to capture, manage, search, and export Markdown notes stored in JSON format.

## Features

- Fast note creation, editing, and deletion.
- Tag management and tag-based filtering.
- Full-text search across titles, bodies, and tags.
- Terminal note preview and single-note Markdown export.

## Usage

```bash
# Add a note
python main.py add "Meeting Notes" "Discussed architecture roadmap" -t work python architecture

# List notes
python main.py list

# Full-text search
python main.py search "roadmap"

# Terminal preview
python main.py show <note_id>

# Export to Markdown
python main.py export <note_id> -o ./exported_note.md
```

## Requirements

Python 3.8+ (Standard Library only).
