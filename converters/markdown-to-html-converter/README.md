# Markdown to HTML Converter

A pure Python standard-library converter that parses Markdown files into complete, standalone HTML5 documents embedded with modern CSS styling templates.

## Features

- **Standard Markdown Elements**: Headings (`#`-`######`), lists (ordered/unordered), code blocks (` ``` `), inline code, bold, italics, links, images, blockquotes, horizontal rules (`---`), and tables.
- **Embedded CSS Themes**: Built-in CSS templates (e.g. `github`, `minimal`, `dark`) for responsive rendering.
- **Pure Standard Library**: No external dependencies required.

## Usage

```bash
# Convert markdown file to styled HTML page
python main.py README.md --output README.html --title "Documentation"

# Use dark theme template
python main.py docs.md --output docs.html --theme dark
```

## Running Tests

```bash
python -m unittest discover -s tests
```
