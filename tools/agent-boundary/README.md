# Agent Boundary Tool

Maintain a hunk-level provenance ledger for human vs AI coding agent edits to track line ownership, detect overwritten human edits, and flag scope boundary violations.

## Features
- Records edit sessions with line-level author attribution (`HUMAN` vs `AGENT`).
- Detects when an AI agent overwrites lines previously authored by human engineers.
- Enforces scope boundary rules (allowed file patterns) for AI agents.
- Generates repository-wide contribution and scope compliance reports.

## Usage

### Record an edit session
```bash
python main.py record --file src/app.py --author-type AGENT --author-name "AI-Assistant" --scope "src/*"
```

### Generate contribution & boundary report
```bash
python main.py report --ledger provenance_ledger.json
```
