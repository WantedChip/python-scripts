# Typing Speed Test CLI

A terminal-based typing speed and accuracy testing utility.

## Features
- **Passage Library**: Includes preset passages with easy, medium, and hard difficulty levels.
- **Timing & Metrics**: Calculates gross WPM, net WPM, character-level accuracy percentage, and typing duration.
- **Error Highlighting**: Pinpoints exact positions where mistyped characters occurred.
- **Score History**: Saves test results to a persistent JSON history file (`typing_history.json`).

## Usage

```bash
# Run a random typing test
python main.py

# Select specific difficulty (easy, medium, hard)
python main.py --difficulty easy

# View past score history
python main.py --history

# List available passages
python main.py --list-passages

# Add a custom passage to the library
python main.py --add-passage "The quick brown fox jumps over the lazy dog." --difficulty easy
```

## Running Tests

```bash
python -m unittest discover -s tests
```
