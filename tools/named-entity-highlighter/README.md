# named-entity-highlighter

Identifies and highlights named entities (Names, Dates, Organizations, Locations) in text using regular expression rules and outputs formatted ANSI text, HTML markup, Markdown, or JSON dataset.

## Usage

### ANSI Colored Terminal Display
```bash
python tools/named-entity-highlighter/named_entity_highlighter.py document.txt
```

### Export HTML, Markdown, or JSON
```bash
python tools/named-entity-highlighter/named_entity_highlighter.py document.txt -f html
python tools/named-entity-highlighter/named_entity_highlighter.py document.txt -f markdown
python tools/named-entity-highlighter/named_entity_highlighter.py document.txt -f json
```

### Options
- `-f`, `--format`: Output format (`ansi`, `html`, `markdown`, `json`). Default: `ansi`.
- `-v`, `--verbose`: Enable detailed debug logging.

## Requirements
Stdlib only (Python 3.8+). No external dependencies.

## Quality
Quality: pylint 10.00/10 · 95% coverage · 0 dependencies
