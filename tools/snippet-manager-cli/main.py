"""CLI Code Snippet Manager.

Stores, tags, searches, formats, and exports code snippets using SQLite storage.
"""

from __future__ import annotations

import argparse
import sqlite3
import subprocess  # nosec B404
import sys
from typing import Any, Dict, List, Optional

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods
# pylint: disable=import-outside-toplevel,consider-using-with,line-too-long


DEFAULT_DB_PATH = "snippets.db"


class SnippetManager:
    """Database manager for code snippet storage and retrieval."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        """Initialize database connection and schema.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS snippets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    language TEXT NOT NULL,
                    code TEXT NOT NULL,
                    description TEXT,
                    tags TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def add_snippet(
        self,
        title: str,
        language: str,
        code: str,
        tags: str = "",
        description: str = "",
    ) -> int:
        """Add a new code snippet to storage.

        Args:
            title: Snippet title.
            language: Programming language / syntax tag.
            code: Source code string.
            tags: Comma-separated tags.
            description: Optional summary description.

        Returns:
            ID of inserted snippet.
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO snippets (title, language, code, tags, description)
                VALUES (?, ?, ?, ?, ?)
                """,
                (title, language.lower(), code, tags.lower(), description),
            )
            conn.commit()
            return cursor.lastrowid or 0

    def list_snippets(
        self, language: Optional[str] = None, tag: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List snippets with optional language and tag filters."""
        query = "SELECT id, title, language, tags, created_at FROM snippets WHERE 1=1"  # nosec B608 # noqa: E501
        params: List[Any] = []

        if language:
            query += " AND language = ?"
            params.append(language.lower())
        if tag:
            query += " AND tags LIKE ?"
            params.append(f"%{tag.lower()}%")

        query += " ORDER BY id DESC"

        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]

    def search_snippets(self, keyword: str) -> List[Dict[str, Any]]:
        """Search snippets across title, code, description, and tags."""
        pattern = f"%{keyword.lower()}%"
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            query = "SELECT id, title, language, tags, created_at FROM snippets WHERE LOWER(title) LIKE ? OR LOWER(code) LIKE ? OR LOWER(description) LIKE ? OR LOWER(tags) LIKE ? ORDER BY id DESC"  # nosec B608 # noqa: E501
            cursor.execute(query, (pattern, pattern, pattern, pattern))
            return [dict(r) for r in cursor.fetchall()]

    def get_snippet(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Retrieve full snippet object by numeric ID or exact title."""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if identifier.isdigit():
                cursor.execute(
                    "SELECT * FROM snippets WHERE id = ?", (int(identifier),)
                )
            else:
                cursor.execute(
                    "SELECT * FROM snippets WHERE LOWER(title) = LOWER(?)",
                    (identifier,),
                )
            row = cursor.fetchone()
            return dict(row) if row else None

    def delete_snippet(self, snippet_id: int) -> bool:
        """Delete snippet by ID."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM snippets WHERE id = ?", (snippet_id,))
            conn.commit()
            return cursor.rowcount > 0

    def copy_to_clipboard(self, text: str) -> bool:
        """Attempt copying snippet text to system clipboard."""
        try:
            import pyperclip

            pyperclip.copy(text)
            return True
        except ImportError:
            pass

        # Try OS native utilities
        if sys.platform == "win32":
            try:
                proc = subprocess.Popen(  # nosec
                    ["clip"],
                    stdin=subprocess.PIPE,
                    text=True,
                )
                proc.communicate(input=text)
                return True
            except Exception:  # pylint: disable=broad-exception-caught
                return False

        if sys.platform == "darwin":
            try:
                proc = subprocess.Popen(  # nosec
                    ["pbcopy"],
                    stdin=subprocess.PIPE,
                    text=True,
                )
                proc.communicate(input=text)
                return True
            except Exception:  # pylint: disable=broad-exception-caught
                return False

        return False


def format_snippet_display(snippet: Dict[str, Any]) -> str:
    """Format snippet details for console display."""
    lines = [
        f"=== Snippet #{snippet['id']}: {snippet['title']} ===",
        (f"Language: {snippet['language']} | Tags:" f" {snippet['tags'] or 'None'}"),
        f"Created: {snippet['created_at']}",
    ]
    if snippet.get("description"):
        lines.append(f"Description: {snippet['description']}")
    lines.append("-" * 50)

    code_lines = snippet["code"].splitlines()
    for idx, line in enumerate(code_lines, 1):
        lines.append(f"{idx:3d} | {line}")

    lines.append("-" * 50)
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description="CLI Code Snippet Manager")
    subparsers = parser.add_subparsers(dest="command", help="Subcommands")

    add_parser = subparsers.add_parser("add", help="Add a new snippet")
    add_parser.add_argument("title", help="Snippet title")
    add_parser.add_argument(
        "--lang", required=True, help="Language (e.g. python, js, sql)"
    )
    add_parser.add_argument("--code", required=True, help="Code content string")
    add_parser.add_argument("--tags", default="", help="Comma separated tags")
    add_parser.add_argument("--description", default="", help="Summary description")

    list_parser = subparsers.add_parser("list", help="List snippets")
    list_parser.add_argument("--lang", help="Filter by language")
    list_parser.add_argument("--tag", help="Filter by tag")

    search_parser = subparsers.add_parser("search", help="Search snippets by keyword")
    search_parser.add_argument("keyword", help="Search keyword")

    show_parser = subparsers.add_parser("show", help="Show snippet details")
    show_parser.add_argument("id_or_title", help="Snippet ID or title")

    copy_parser = subparsers.add_parser("copy", help="Copy snippet code to clipboard")
    copy_parser.add_argument("id_or_title", help="Snippet ID or title")

    del_parser = subparsers.add_parser("delete", help="Delete snippet")
    del_parser.add_argument("id", type=int, help="Snippet ID")

    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entrypoint for Snippet Manager CLI."""
    parser = build_parser()
    parsed = parser.parse_args(args)
    mgr = SnippetManager()

    if parsed.command == "add":
        sid = mgr.add_snippet(
            title=parsed.title,
            language=parsed.lang,
            code=parsed.code,
            tags=parsed.tags,
            description=parsed.description,
        )
        print(f"Added snippet #{sid}: '{parsed.title}'")
    elif parsed.command == "list":
        snippets = mgr.list_snippets(language=parsed.lang, tag=parsed.tag)
        print(f"Found {len(snippets)} snippets:")
        for s in snippets:
            print(
                f"  [{s['id']}] {s['title']} ({s['language']}) - Tags:" f" {s['tags']}"
            )
    elif parsed.command == "search":
        snippets = mgr.search_snippets(parsed.keyword)
        print(f"Search results for '{parsed.keyword}':")
        for s in snippets:
            print(
                f"  [{s['id']}] {s['title']} ({s['language']}) - Tags:" f" {s['tags']}"
            )
    elif parsed.command == "show":
        s_show = mgr.get_snippet(parsed.id_or_title)
        if s_show:
            print(format_snippet_display(s_show))
        else:
            print("Snippet not found.")
    elif parsed.command == "copy":
        s_copy = mgr.get_snippet(parsed.id_or_title)
        if s_copy:
            success = mgr.copy_to_clipboard(s_copy["code"])
            if success:
                print(f"Copied snippet #{s_copy['id']} code to clipboard!")
            else:
                print("Could not access system clipboard, printing code:")
                print(s_copy["code"])
        else:
            print("Snippet not found.")
    elif parsed.command == "delete":
        if mgr.delete_snippet(parsed.id):
            print(f"Deleted snippet #{parsed.id}.")
        else:
            print("Snippet ID not found.")
    else:
        parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())
