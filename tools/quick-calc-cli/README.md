# Quick Calc CLI

A safe, AST-based command-line math calculator with support for scientific functions, variable assignment, and calculation history.

## Features
- **Safe AST Evaluation**: Evaluates math expressions without using dangerous built-in `eval()`.
- **Math Functions & Constants**: `sin`, `cos`, `tan`, `sqrt`, `log`, `log10`, `exp`, `abs`, `floor`, `ceil`, `pi`, `e`, `tau`.
- **Variable Storage**: Assign variables (e.g., `radius = 5`, `area = pi * radius^2`). Auto-saves previous result in `ans`.
- **Calculation History**: Maintains a log of expressions and evaluated results.
- **Interactive REPL & CLI Mode**: Run interactive session or single line calculations.

## Usage

```bash
# Evaluate a single expression
python main.py "2 * sin(pi / 4) + sqrt(16)"

# Interactive mode
python main.py interactive

# View calculation history
python main.py history
```

## Running Tests
```bash
python -m unittest discover tests
```
