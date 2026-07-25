# Joke Fetcher

A CLI tool that fetches programming, general, or pun jokes from JokeAPI (v2) with safe mode support.

## Features

- Fetch jokes by category (`Programming`, `Misc`, `Pun`, etc.)
- Parse single and two-part jokes
- Safe mode flag enabled by default (disable with `--unsafe`)
- Clean console presentation

## Usage

```bash
python main.py
python main.py --category Programming
python main.py --category Pun --unsafe
```

## Running Tests

```bash
python -m unittest discover -s tests
```
