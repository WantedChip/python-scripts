# AI Code Sanitizer

Scans source code likely generated or heavily modified by AI and flags common quality bugs such as fake imports, nonexistent package APIs, duplicate helpers, placeholder comments, swallowed exceptions, unnecessary abstractions, and non-verifying test routines.

## Quality Metadata
Quality: pylint 10.00/10 · 85% coverage · 0 dependencies

## Features

- **Fake Imports & Nonexistent APIs**: Uses python path inspection and local resolution to flag hallucinated imports or missing function imports from standard modules.
- **Duplicate Helpers**: Matches structural similarity of functions (via AST normalization) and identifies redundant functions with similar names or implementation blocks.
- **Placeholder Comments**: Flags leftover development comments (e.g. `# TODO: add implementation`).
- **Swallowed Exceptions**: Checks for empty `except Exception:` blocks that pass or print without re-raising or logging the error.
- **Unnecessary Abstractions**: Flags class declarations with only a single method and trivial wrapper functions forwarding all arguments to another function.
- **Non-Verifying Tests**: Warns when test functions contain no assertion statements (or only trivial ones like `assert True`).

## Usage

Run the sanitizer directly against any Python file:

```bash
python checkers/ai-code-sanitizer/ai_code_sanitizer.py path/to/target_file.py
```

## Running Tests

Run the test suite and verify line coverage:

```bash
pytest checkers/ai-code-sanitizer/tests/test_ai_code_sanitizer.py --cov=checkers/ai-code-sanitizer/ai_code_sanitizer --cov-report=term-missing
```
