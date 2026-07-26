"""Bookmark Manager CLI.

Command-line URL bookmark manager supporting CRUD, tag filtering,
full-text search, dead link validation, and browser launching.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,redefined-builtin

import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.request
import webbrowser
from typing import Any, Dict, List, Optional

STORAGE_FILE = "bookmarks.json"


class Bookmark:
    """Represents a single URL bookmark model."""

    def __init__(
        self,
        id: int,
        url: str,
        title: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        created_at: Optional[str] = None,
        last_status: Optional[int] = None,
    ) -> None:
        self.id = id
        self.url = url
        self.title = title
        self.description = description
        self.tags = tags if tags is not None else []
        self.created_at = created_at or datetime.datetime.now().isoformat()
        self.last_status = last_status

    def to_dict(self) -> Dict[str, Any]:
        """Converts bookmark instance to a JSON-serializable dictionary."""
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "description": self.description,
            "tags": self.tags,
            "created_at": self.created_at,
            "last_status": self.last_status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Bookmark":
        """Creates a Bookmark instance from a dictionary."""
        return cls(
            id=data["id"],
            url=data["url"],
            title=data["title"],
            description=data.get("description", ""),
            tags=data.get("tags", []),
            created_at=data.get("created_at"),
            last_status=data.get("last_status"),
        )


class BookmarkManager:
    """Manages bookmark persistence, CRUD, filtering, search, and validation."""

    def __init__(self, filepath: str = STORAGE_FILE) -> None:
        self.filepath = filepath
        self.bookmarks: List[Bookmark] = self.load()

    def load(self) -> List[Bookmark]:
        """Loads bookmarks from storage file."""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return [Bookmark.from_dict(b) for b in data]
            except (json.JSONDecodeError, OSError, ValueError, KeyError):
                return []
        return []

    def save(self) -> None:
        """Saves current bookmarks list to storage file."""
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump([b.to_dict() for b in self.bookmarks], f, indent=2)

    def _generate_id(self) -> int:
        """Generates unique incremental ID."""
        if not self.bookmarks:
            return 1
        return max(b.id for b in self.bookmarks) + 1

    def add_bookmark(
        self,
        url: str,
        title: str,
        description: str = "",
        tags: Optional[List[str]] = None,
    ) -> Bookmark:
        """Adds a new bookmark."""
        b_id = self._generate_id()
        bookmark = Bookmark(
            id=b_id, url=url, title=title, description=description, tags=tags
        )
        self.bookmarks.append(bookmark)
        self.save()
        return bookmark

    def get_bookmark(self, b_id: int) -> Optional[Bookmark]:
        """Retrieves a bookmark by ID."""
        for b in self.bookmarks:
            if b.id == b_id:
                return b
        return None

    def update_bookmark(
        self,
        b_id: int,
        url: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Optional[Bookmark]:
        """Updates an existing bookmark by ID."""
        bookmark = self.get_bookmark(b_id)
        if not bookmark:
            return None

        if url is not None:
            bookmark.url = url
        if title is not None:
            bookmark.title = title
        if description is not None:
            bookmark.description = description
        if tags is not None:
            bookmark.tags = tags

        self.save()
        return bookmark

    def delete_bookmark(self, b_id: int) -> bool:
        """Deletes a bookmark by ID."""
        initial_len = len(self.bookmarks)
        self.bookmarks = [b for b in self.bookmarks if b.id != b_id]
        if len(self.bookmarks) < initial_len:
            self.save()
            return True
        return False

    def filter_by_tag(self, tag: str) -> List[Bookmark]:
        """Filters bookmarks matching specific tag."""
        tag_lower = tag.lower().strip()
        return [
            b for b in self.bookmarks if any(t.lower() == tag_lower for t in b.tags)
        ]

    def search(self, query: str) -> List[Bookmark]:
        """Performs full-text search across title, description, URL, tags."""
        q_lower = query.lower()
        results: List[Bookmark] = []
        for b in self.bookmarks:
            in_title = q_lower in b.title.lower()
            in_desc = q_lower in b.description.lower()
            in_url = q_lower in b.url.lower()
            in_tags = any(q_lower in t.lower() for t in b.tags)
            if in_title or in_desc or in_url or in_tags:
                results.append(b)
        return results

    def validate_link(self, bookmark: Bookmark, timeout: int = 5) -> int:
        """Validates URL accessibility via HTTP request.

        Returns HTTP status code or 0 if connection failed.
        """
        user_agent = "Mozilla/5.0 (BookmarkManagerCLI/1.0)"
        req = urllib.request.Request(
            bookmark.url,
            headers={"User-Agent": user_agent},
            method="HEAD",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
                status = resp.status
        except urllib.error.HTTPError as e:
            status = e.code
        except (urllib.error.URLError, OSError, ValueError):
            # Retry with GET method if HEAD is rejected or fails
            try:
                get_req = urllib.request.Request(
                    bookmark.url,
                    headers={"User-Agent": user_agent},
                )
                with urllib.request.urlopen(
                    get_req, timeout=timeout
                ) as resp:  # nosec B310
                    status = resp.status
            except urllib.error.HTTPError as e:
                status = e.code
            except (urllib.error.URLError, OSError, ValueError):
                status = 0

        bookmark.last_status = int(status)
        return int(status)

    def validate_all(self, timeout: int = 5) -> Dict[int, int]:
        """Validates all stored bookmarks and saves updated statuses."""
        results: Dict[int, int] = {}
        for b in self.bookmarks:
            status = self.validate_link(b, timeout=timeout)
            results[b.id] = status
        self.save()
        return results

    @staticmethod
    def open_in_browser(url: str) -> bool:
        """Opens URL in default system web browser."""
        return webbrowser.open(url)


def print_bookmark(b: Bookmark) -> None:
    """Utility to print formatted bookmark details."""
    tags_str = ", ".join(b.tags) if b.tags else "None"
    s_val = b.last_status
    status_str = f" [HTTP {s_val}]" if s_val is not None else ""
    print(f"[{b.id}] {b.title}{status_str}")
    print(f"     URL : {b.url}")
    if b.description:
        print(f"     Desc: {b.description}")
    print(f"     Tags: {tags_str}")
    print("-" * 50)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Bookmark Manager CLI"
    parser = argparse.ArgumentParser(description=desc)
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Add command
    add_parser = subparsers.add_parser("add", help="Add a new bookmark")
    add_parser.add_argument("--url", required=True, help="URL of the bookmark")
    add_parser.add_argument("--title", required=True, help="Title of the bookmark")
    add_parser.add_argument("--description", default="", help="Description")
    add_parser.add_argument("--tags", default="", help="Comma-separated tags")

    # List command
    list_parser = subparsers.add_parser("list", help="List bookmarks")
    list_parser.add_argument("--tag", help="Filter by tag")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search bookmarks")
    search_parser.add_argument("query", help="Search query string")

    # Update command
    up_help = "Update existing bookmark"
    update_parser = subparsers.add_parser("update", help=up_help)
    update_parser.add_argument("--id", type=int, required=True, help="Bookmark ID")
    update_parser.add_argument("--url", help="New URL")
    update_parser.add_argument("--title", help="New Title")
    update_parser.add_argument("--description", help="New Description")
    update_parser.add_argument("--tags", help="New comma-separated tags")

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a bookmark")
    delete_parser.add_argument("--id", type=int, required=True, help="Bookmark ID")

    # Validate command
    subparsers.add_parser("validate", help="Validate all bookmark HTTP links")

    # Open command
    open_parser = subparsers.add_parser("open", help="Open bookmark in web browser")
    open_parser.add_argument("--id", type=int, required=True, help="Bookmark ID")
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI Entry point."""
    parser = build_parser()
    parsed = parser.parse_args(args)
    mgr = BookmarkManager()

    if parsed.command == "add":
        tags = [t.strip() for t in parsed.tags.split(",") if t.strip()]
        new_b = mgr.add_bookmark(parsed.url, parsed.title, parsed.description, tags)
        print(f"Added bookmark [{new_b.id}] '{new_b.title}'")

    elif parsed.command == "list":
        if parsed.tag:
            items = mgr.filter_by_tag(parsed.tag)
            print(f"\n=== Bookmarks tagged with '{parsed.tag}' ===")
        else:
            items = mgr.bookmarks
            print("\n=== All Bookmarks ===")

        if not items:
            print("No bookmarks found.")
        else:
            for item in items:
                print_bookmark(item)

    elif parsed.command == "search":
        items = mgr.search(parsed.query)
        print(f"\n=== Search results for '{parsed.query}' ===")
        if not items:
            print("No matching bookmarks found.")
        else:
            for item in items:
                print_bookmark(item)

    elif parsed.command == "update":
        if parsed.tags is not None:
            tags = [t.strip() for t in parsed.tags.split(",") if t.strip()]
        else:
            tags = None

        up_b = mgr.update_bookmark(
            parsed.id,
            url=parsed.url,
            title=parsed.title,
            description=parsed.description,
            tags=tags,
        )
        if up_b:
            print(f"Updated bookmark [{up_b.id}]")
        else:
            print(f"Bookmark with ID {parsed.id} not found.")

    elif parsed.command == "delete":
        if mgr.delete_bookmark(parsed.id):
            print(f"Deleted bookmark [{parsed.id}]")
        else:
            print(f"Bookmark with ID {parsed.id} not found.")

    elif parsed.command == "validate":
        print("Validating bookmark URLs...")
        results = mgr.validate_all()
        print("\n=== Validation Results ===")
        for b_id, status in results.items():
            val_b = mgr.get_bookmark(b_id)
            title = val_b.title if val_b else "Unknown"
            if status > 0:
                s_desc = f"HTTP {status}"
            else:
                s_desc = "UNREACHABLE / DEAD LINK"
            print(f"[{b_id}] {title}: {s_desc}")

    elif parsed.command == "open":
        open_b = mgr.get_bookmark(parsed.id)
        if open_b:
            print(f"Opening '{open_b.url}' in browser...")
            mgr.open_in_browser(open_b.url)
        else:
            print(f"Bookmark with ID {parsed.id} not found.")

    else:
        parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())
