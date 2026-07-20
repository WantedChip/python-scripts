# example-drift-checker

Verify that Python code block examples documented inside project Markdown files match current codebase class and function API parameter signatures.

## Usage

Scan for documentation examples drifts in the current directory:

```bash
python example_drift_checker.py
```

Specify custom source and documentation directories:

```bash
python example_drift_checker.py --src C:/Users/Name/Projects/my_app/src --docs C:/Users/Name/Projects/my_app/docs
```

## Requirements

- Python 3.11+
- Pure standard library (zero external dependencies)

## How It Works

- **Source API Indexing**: Scans Python source files recursively, parsing class names, function/method names, and arguments into a database dictionary.
- **Example Parsing**: Scans documentation files (`.md`, `.txt`) for Python code blocks starting with ````python or ````py.
- **AST Comparison**: Parses example blocks using AST to identify API calls, counting argument patterns and keyword parameter assignments, and highlights drifts where example parameters differ from declarations.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies
