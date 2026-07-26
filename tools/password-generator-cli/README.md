# Password Generator CLI

A cryptographically secure password and passphrase generator using Python's `secrets` module, complete with entropy rating calculations.

## Features

- Cryptographically secure generation (`secrets` module).
- Character set toggles (uppercase, lowercase, digits, symbols).
- Custom character exclusion list (e.g., ambiguous characters like `lI1O0`).
- Memorable passphrase mode.
- Entropy bit calculation and visual security rating.

## Usage

```bash
# Generate 16-character random password
python main.py password --length 16

# Exclude ambiguous characters and symbols
python main.py password --length 20 --no-symbols --exclude "lI1O0"

# Generate memorable 5-word passphrase
python main.py passphrase --words 5 --separator "-"
```

## Requirements

Python 3.8+ (Standard Library only).
