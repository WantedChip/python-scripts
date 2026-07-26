# Snippet Manager CLI

A command-line code snippet manager for storing, tagging, searching, formatting, and copying code snippets across languages.

## Features
- **Snippet Storage**: SQLite database backend storing titles, code blocks, programming languages, descriptions, and tags.
- **Language & Tag Filtering**: Filter snippets by programming language (python, javascript, sql, etc.) or tags.
- **Full-Text Keyword Search**: Search across titles, code content, descriptions, and syntax tags.
- **Formatted Display**: View code snippets with line numbers and syntax metadata headers.
- **Clipboard Export**: Copy snippets directly to system clipboard or stdout stream.

## Usage

```bash
# Add a code snippet
python main.py add "Quick Sort" --lang python --code "def quicksort(arr): return arr" --tags "algorithm,sorting"

# List snippets filtered by language
python main.py list --lang python

# Search snippets by keyword or tag
python main.py search "sorting"

# Show formatted snippet details
python main.py show 1

# Copy snippet code to clipboard
python main.py copy 1

# Delete a snippet
python main.py delete 1
```

## Running Tests
```bash
python -m unittest discover tests
```
