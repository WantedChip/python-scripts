# Clipboard History Tool

A command-line clipboard history manager featuring search, recall, deduplication, and automatic secret redaction.

## Features
- **Auto-Redaction**: Automatically masks API keys, passwords, bearer tokens, and private keys before storing.
- **Deduplication**: Prevents consecutive duplicate entries from clogging history.
- **Search & Filter**: Search clipboard history by keyword or tag.
- **Export & Import**: Export history to JSON or plain text formats.
- **SQLite Storage**: Persistent history storage with metadata and timestamps.

## Usage

```bash
# Add an entry manually
python main.py add "API key: sk-abcdef1234567890abcdef1234567890"

# List recent clipboard entries
python main.py list --limit 10

# Search clipboard history
python main.py search --query "API key"

# Export history to JSON
python main.py export --output history.json

# Clear history
python main.py clear
```

## Running Tests
```bash
python -m unittest discover tests
```
