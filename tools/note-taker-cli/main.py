"""Note Taker CLI tool.

Command-line note capture tool supporting note creation/editing, tag management,
full-text search, Markdown preview & export, and JSON file storage.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import json
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_NOTES_FILE = Path.home() / ".note_taker_cli.json"


class NoteStore:
    """Manages reading, searching, and persisting notes to JSON storage."""

    def __init__(self, storage_file: Path = DEFAULT_NOTES_FILE):
        self.storage_file = storage_file
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)

    def _load_notes(self) -> List[Dict[str, Any]]:
        if not self.storage_file.exists():
            return []
        try:
            with open(self.storage_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                return []
        except (json.JSONDecodeError, OSError):
            return []

    def _save_notes(self, notes: List[Dict[str, Any]]) -> None:
        with open(self.storage_file, "w", encoding="utf-8") as f:
            json.dump(notes, f, indent=2)

    def create_note(
        self, title: str, body: str, tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create a new note entry."""
        notes = self._load_notes()
        now = datetime.now().isoformat()
        cleaned_tags = [t.strip().lower() for t in (tags or []) if t.strip()]

        # Generate short 6-char unique ID
        note_id = str(uuid.uuid4())[:6]

        note = {
            "id": note_id,
            "title": title,
            "body": body,
            "tags": cleaned_tags,
            "created_at": now,
            "updated_at": now,
        }
        notes.append(note)
        self._save_notes(notes)
        return note

    def get_note(self, note_id: str) -> Optional[Dict[str, Any]]:
        """Get note by ID."""
        notes = self._load_notes()
        for note in notes:
            if note["id"] == note_id:
                return note
        return None

    def edit_note(
        self,
        note_id: str,
        title: Optional[str] = None,
        body: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update an existing note."""
        notes = self._load_notes()
        for note in notes:
            if note["id"] == note_id:
                if title is not None:
                    note["title"] = title
                if body is not None:
                    note["body"] = body
                if tags is not None:
                    c_tags = [t.strip().lower() for t in tags if t.strip()]
                    note["tags"] = c_tags
                note["updated_at"] = datetime.now().isoformat()
                self._save_notes(notes)
                return note
        return None

    def delete_note(self, note_id: str) -> bool:
        """Delete a note by ID."""
        notes = self._load_notes()
        filtered = [n for n in notes if n["id"] != note_id]
        if len(filtered) < len(notes):
            self._save_notes(filtered)
            return True
        return False

    def list_notes(self, tag_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all notes, optionally filtered by tag."""
        notes = self._load_notes()
        if tag_filter:
            tag_clean = tag_filter.strip().lower()
            notes = [n for n in notes if tag_clean in n.get("tags", [])]
        return sorted(notes, key=lambda x: x["updated_at"], reverse=True)

    def search_notes(self, query: str) -> List[Dict[str, Any]]:
        """Full-text search matching title, body, or tags."""
        notes = self._load_notes()
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        results = []
        for note in notes:
            tags_str = " ".join(note.get("tags", []))
            match_t = pattern.search(note["title"])
            match_b = pattern.search(note["body"])
            match_tag = pattern.search(tags_str)
            if match_t or match_b or match_tag:
                results.append(note)
        return sorted(results, key=lambda x: x["updated_at"], reverse=True)


def export_note_as_markdown(note: Dict[str, Any], output_path: Path) -> Path:
    """Export a note to a standalone Markdown file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tags_line = ", ".join(note.get("tags", []))
    c_at = note["created_at"]
    u_at = note["updated_at"]
    content = (
        f"# {note['title']}\n\n"
        f"*Created: {c_at} | Updated: {u_at} | Tags: {tags_line}*\n\n"
        f"---\n\n{note['body']}\n"
    )
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


def render_preview(note: Dict[str, Any]) -> str:
    """Render terminal preview of a Markdown note."""
    t_list = note.get("tags", [])
    tags_str = f"[{', '.join(t_list)}]" if t_list else "[]"
    header = f"=== [{note['id']}] {note['title']} {tags_str} ==="
    border = "=" * len(header)
    return f"{header}\n{note['body']}\n{border}"


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description="Command-line Note Taker tool")
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_NOTES_FILE,
        help="JSON storage file path",
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommands")

    # Add
    add_parser = subparsers.add_parser("add", help="Add a new note")
    add_parser.add_argument("title", help="Note title")
    add_parser.add_argument("body", help="Note body text")
    add_parser.add_argument("-t", "--tags", nargs="*", default=[], help="Tags list")

    # List
    list_parser = subparsers.add_parser("list", help="List notes")
    list_parser.add_argument("-t", "--tag", help="Filter notes by tag")

    # Search
    search_parser = subparsers.add_parser("search", help="Search notes")
    search_parser.add_argument("query", help="Search query string")

    # Edit
    edit_parser = subparsers.add_parser("edit", help="Edit note")
    edit_parser.add_argument("id", help="Note ID")
    edit_parser.add_argument("--title", help="New title")
    edit_parser.add_argument("--body", help="New body")
    edit_parser.add_argument("-t", "--tags", nargs="*", help="New tags list")

    # Show / Preview
    show_parser = subparsers.add_parser("show", help="Preview note content")
    show_parser.add_argument("id", help="Note ID")

    # Export
    ex_help = "Export note to Markdown file"
    export_parser = subparsers.add_parser("export", help=ex_help)
    export_parser.add_argument("id", help="Note ID")
    export_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output Markdown file path",
    )

    # Delete
    del_parser = subparsers.add_parser("delete", help="Delete note")
    del_parser.add_argument("id", help="Note ID")
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entrypoint for Note Taker."""
    parser = build_parser()
    parsed = parser.parse_args(args)
    store = NoteStore(parsed.file)

    if parsed.command == "add":
        note = store.create_note(parsed.title, parsed.body, parsed.tags)
        print(f"Created note [{note['id']}] '{note['title']}'.")

    elif parsed.command == "list" or parsed.command is None:
        tag = getattr(parsed, "tag", None)
        notes = store.list_notes(tag_filter=tag)
        print(f"\n--- Notes ({len(notes)}) ---")
        for n in notes:
            tags_str = f"[{', '.join(n['tags'])}]" if n["tags"] else ""
            upd = n["updated_at"][:10]
            print(f"[{n['id']}] {n['title']} {tags_str} ({upd})")

    elif parsed.command == "search":
        results = store.search_notes(parsed.query)
        print(f"\n--- Search Results for '{parsed.query}' ({len(results)}) ---")
        for n in results:
            print(f"[{n['id']}] {n['title']} ({n['updated_at'][:10]})")

    elif parsed.command == "edit":
        edited_note = store.edit_note(
            parsed.id, title=parsed.title, body=parsed.body, tags=parsed.tags
        )
        if edited_note:
            print(f"Updated note [{edited_note['id']}].")
        else:
            print(f"Note [{parsed.id}] not found.")

    elif parsed.command == "show":
        show_note = store.get_note(parsed.id)
        if show_note:
            print(render_preview(show_note))
        else:
            print(f"Note [{parsed.id}] not found.")

    elif parsed.command == "export":
        exp_note = store.get_note(parsed.id)
        if exp_note:
            out_file = export_note_as_markdown(exp_note, parsed.output)
            print(f"Exported note [{parsed.id}] to {out_file}.")
        else:
            print(f"Note [{parsed.id}] not found.")

    elif parsed.command == "delete":
        if store.delete_note(parsed.id):
            print(f"Deleted note [{parsed.id}].")
        else:
            print(f"Note [{parsed.id}] not found.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
