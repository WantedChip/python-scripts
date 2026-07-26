# Bookmark Manager CLI

Command-line URL bookmark manager with tagging, search, HTTP status validation, and open-in-browser support.

## Features
- **Bookmark CRUD**: Add, list, update, and delete bookmarks.
- **Tag Filtering**: Filter bookmarks by tags.
- **Full-Text Search**: Search bookmarks across URL, title, description, and tags.
- **Dead Link Validator**: Verify accessibility of bookmarks via HTTP HEAD/GET checks.
- **Browser Launcher**: Open saved bookmarks directly in the default web browser.

## Usage

```bash
# Add a bookmark
python main.py add --url "https://python.org" --title "Python Official Site" --description "Python language docs and news" --tags "python,programming,docs"

# List all bookmarks
python main.py list

# Filter bookmarks by tag
python main.py list --tag programming

# Full-text search
python main.py search "language docs"

# Update a bookmark
python main.py update --id 1 --title "Python Language Site"

# Delete a bookmark
python main.py delete --id 1

# Check for dead links (HTTP status check)
python main.py validate

# Open bookmark in browser
python main.py open --id 1
```

## Running Tests

```bash
python -m unittest discover -s tests
```
