# Terminal Presentation Tool

Turn Markdown documents into clean, interactive terminal-native presentations with syntax highlighting and live code snippet execution.

## Features
- **Markdown Slide Parsing**: Split presentations using `---` dividers or `# ` headers.
- **Terminal Rendering**: Custom ANSI syntax highlighting for Markdown headers, list items, bold text, and code blocks.
- **Live Snippet Execution**: Execute shell commands or Python snippets embedded in slides (` ```bash `, ` ```exec `) live in the terminal.
- **Interactive Navigation**: Move through slides using keyboard controls (`n`ext, `p`revious, `e`xecute snippet, `q`uit).
- **Non-Interactive Mode**: Export rendered slides to ANSI text files or view specific slides in headless/scripted environments.

## Usage

### Launch presentation interactively
```bash
python main.py presentation.md
```

### Auto-run code snippets live
```bash
python main.py presentation.md --run-code
```

### Non-interactive rendering / export
```bash
python main.py presentation.md --slide 1 --non-interactive
python main.py presentation.md --export-text rendered_deck.txt
```
