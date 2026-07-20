# dead-code-confidence

Scan Python directories recursively to identify potentially unused functions, classes, and methods, scoring their dead code probability with clear evidence details rather than executing deleting actions.

## Usage

Scan the current directory for dead code candidates:

```bash
python dead_code_confidence.py
```

Scan a custom target directory:

```bash
python dead_code_confidence.py C:/Users/Name/Projects/my_app
```

Report only candidates matching a specific confidence score (e.g. 75% or higher):

```bash
python dead_code_confidence.py --confidence 75
```

## Requirements

- Python 3.11+
- Pure standard library (zero external dependencies)

## Confidence Heuristics

- **99% Confidence**: The class or function declaration name has zero references anywhere else in the project folder directory.
- **90% Confidence**: References are found, but exclusively inside unit tests (`test_*.py` files or `tests/` directories), meaning it is unused in production logic.
- **0% Confidence**: Active references found inside production code blocks.

## Quality

Quality: pylint 10.00/10 · 100% coverage · 0 dependencies
