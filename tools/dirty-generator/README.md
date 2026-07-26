# Dirty Generator Tool

Profile developer commands (e.g., `npm test`, `pytest`, `make build`) by tracking filesystem side effects and detecting baseline violations.

## Features
- Captures directory file snapshots before and after command execution.
- Tracks created, modified, and deleted files.
- Records and enforces a command mutation baseline (`baseline.json`).
- Flags unapproved dirty side effects as baseline violations.

## Usage

### Profile a command
```bash
python main.py --cmd "pytest" --root .
```

### Record a mutation baseline
```bash
python main.py --cmd "pytest" --root . --baseline-file baseline.json --record-baseline
```

### Run and enforce baseline
```bash
python main.py --cmd "pytest" --root . --baseline-file baseline.json
```
