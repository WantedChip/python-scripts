"""Clipboard History Tool with secret auto-redaction, search, and storage.

Tracks clipboard text entries, redacting sensitive secrets (API keys, passwords)
and persisting entries to a SQLite database.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from typing import Dict, List, Optional, Tuple

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods


DEFAULT_DB_PATH = "clipboard.db"

SECRET_PATTERNS = [
    (
        r"(?i)(api[_-]?key|secret|password|passwd|token|auth)\s*[:=]\s*['\"]?"
        r"([^\s'\"]+)['\"]?",
        r"\1: [REDACTED_SECRET]",
    ),
    (r"sk-[a-zA-Z0-9]{32,}", "[REDACTED_OPENAI_KEY]"),
    (r"AKIA[0-9A-Z]{16}", "[REDACTED_AWS_KEY]"),
    (r"Bearer\s+[a-zA-Z0-9\-\._~\+\/]+=*", "Bearer [REDACTED_TOKEN]"),
    (
        r"-----BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY-----[\s\S]*?"
        r"-----END \1 PRIVATE KEY-----",
        "[REDACTED_PRIVATE_KEY]",
    ),
    (r"ghp_[a-zA-Z0-9]{36}", "[REDACTED_GITHUB_TOKEN]"),
]


class SecretRedactor:
    """Utility class for detecting and auto-redacting sensitive content."""

    def __init__(self, patterns: Optional[List[Tuple[str, str]]] = None) -> None:
        """Initialize redactor with custom or default regex patterns."""
        self.patterns = patterns if patterns is not None else SECRET_PATTERNS

    def redact(self, text: str) -> str:
        """Redact sensitive patterns from given text.

        Args:
            text: Input raw string.

        Returns:
            Sanitized string with sensitive tokens replaced.
        """
        sanitized = text
        for pattern, replacement in self.patterns:
            sanitized = re.sub(pattern, replacement, sanitized)
        return sanitized


class ClipboardManager:
    """Database manager for clipboard history persistence."""

    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        redactor: Optional[SecretRedactor] = None,
    ) -> None:
        """Initialize ClipboardManager with database path and redactor.

        Args:
            db_path: SQLite database file path.
            redactor: Instance of SecretRedactor.
        """
        self.db_path = db_path
        self.redactor = redactor or SecretRedactor()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS clipboard_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    raw_content_preview TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    tags TEXT
                )
                """
            )
            conn.commit()

    def add_entry(
        self, raw_text: str, tags: str = "", redact: bool = True
    ) -> Optional[int]:
        """Add a clipboard entry to history with deduplication and redaction.

        Args:
            raw_text: Content to store.
            tags: Comma-separated tags.
            redact: Whether to run secret auto-redaction.

        Returns:
            Inserted ID or None if duplicate of latest entry.
        """
        if not raw_text.strip():
            return None

        content = self.redactor.redact(raw_text) if redact else raw_text
        preview = raw_text[:30] + ("..." if len(raw_text) > 30 else "")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Check latest entry for deduplication
            q_select = "SELECT content FROM clipboard_history ORDER BY id DESC LIMIT 1"
            cursor.execute(q_select)
            row = cursor.fetchone()
            if row and row[0] == content:
                return None

            q_insert = (
                "INSERT INTO clipboard_history "
                "(content, raw_content_preview, tags) VALUES (?, ?, ?)"
            )
            cursor.execute(q_insert, (content, preview, tags))
            conn.commit()
            return cursor.lastrowid

    def list_entries(self, limit: int = 20) -> List[Dict[str, str]]:
        """Retrieve recent clipboard entries.

        Args:
            limit: Maximum entries to return.

        Returns:
            List of dictionaries representing clipboard entries.
        """
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            q_list = (
                "SELECT id, content, created_at, tags "
                "FROM clipboard_history ORDER BY id DESC LIMIT ?"
            )
            cursor.execute(q_list, (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def search_entries(self, query: str) -> List[Dict[str, str]]:
        """Search entries by keyword.

        Args:
            query: Search substring.

        Returns:
            List of matching clipboard entries.
        """
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            pattern = f"%{query}%"
            q_search = (
                "SELECT id, content, created_at, tags "
                "FROM clipboard_history WHERE content LIKE ? OR tags LIKE ? "
                "ORDER BY id DESC"
            )
            cursor.execute(q_search, (pattern, pattern))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def export_entries(self, filepath: str, format_type: str = "json") -> str:
        """Export clipboard history to JSON or TXT file.

        Args:
            filepath: Destination path.
            format_type: 'json' or 'txt'.

        Returns:
            Path of exported file.
        """
        entries = self.list_entries(limit=10000)
        if format_type.lower() == "json":
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=2)
        else:
            with open(filepath, "w", encoding="utf-8") as f:
                for entry in entries:
                    header = f"[{entry['created_at']}] (ID: {entry['id']})\n"
                    f.write(f"{header}{entry['content']}\n{'-'*40}\n")
        return filepath

    def clear_history(self) -> None:
        """Clear all stored clipboard history."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM clipboard_history")
            conn.commit()


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Clipboard History Tool with secret auto-redaction."
    parser = argparse.ArgumentParser(description=desc)
    subparsers = parser.add_subparsers(dest="command", help="Subcommands")

    add_parser = subparsers.add_parser("add", help="Add text to clipboard history")
    add_parser.add_argument("text", help="Text content to store")
    add_parser.add_argument("--tags", default="", help="Comma separated tags")
    add_parser.add_argument(
        "--no-redact",
        action="store_true",
        help="Disable secret auto-redaction",
    )

    list_parser = subparsers.add_parser("list", help="List clipboard history")
    list_parser.add_argument(
        "--limit", type=int, default=10, help="Number of records to return"
    )

    search_parser = subparsers.add_parser("search", help="Search history by query")
    search_parser.add_argument(
        "--query", required=True, help="Keyword or tag to search"
    )

    export_parser = subparsers.add_parser("export", help="Export clipboard history")
    export_parser.add_argument("--output", required=True, help="Destination filepath")
    export_parser.add_argument(
        "--format",
        choices=["json", "txt"],
        default="json",
        help="Export format",
    )

    subparsers.add_parser("clear", help="Clear all clipboard history")
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entrypoint for Clipboard History Tool."""
    parser = build_parser()
    parsed = parser.parse_args(args)
    mgr = ClipboardManager()

    if parsed.command == "add":
        inserted_id = mgr.add_entry(
            parsed.text, tags=parsed.tags, redact=not parsed.no_redact
        )
        if inserted_id:
            print(f"Added clipboard entry ID: {inserted_id}")
        else:
            print("Duplicate or empty entry skipped.")
    elif parsed.command == "list":
        entries = mgr.list_entries(limit=parsed.limit)
        for e in entries:
            print(f"[{e['id']}] {e['created_at']}: {e['content']}")
    elif parsed.command == "search":
        entries = mgr.search_entries(parsed.query)
        print(f"Found {len(entries)} matching entries:")
        for e in entries:
            print(f"[{e['id']}] {e['created_at']}: {e['content']}")
    elif parsed.command == "export":
        out = mgr.export_entries(parsed.output, format_type=parsed.format)
        print(f"Exported history to {out}")
    elif parsed.command == "clear":
        mgr.clear_history()
        print("Clipboard history cleared.")
    else:
        parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())
