# Example Runner Tool

`example-runner` parses Markdown documentation files, extracts embedded code blocks (`python`, `bash`, `sh`), executes them safely inside isolated temporary environments, and checks their outputs to catch outdated or failing documentation examples.

## Usage

```bash
python main.py README.md docs/
```

## Features

- Parses fenced code blocks: ````python` and ````bash`.
- Supports expected output assertions via comments (e.g. `# Expected: Hello World`).
- Runs each snippet in a clean temporary workspace directory with execution timeouts.
- Outputs pass/fail summaries per document file and sets proper exit codes for automated testing.
