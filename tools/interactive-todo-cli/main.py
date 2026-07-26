"""Interactive TODO List Manager CLI tool.

Task CRUD operations, priority levels (High/Medium/Low), tag management,
filtering by tag/status, ASCII table formatting, and SQLite persistence.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods
# pylint: disable=implicit-str-concat

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_DB_FILE = Path.home() / ".todo_cli.db"


class TodoDatabase:
    """Manages SQLite database operations for tasks."""

    def __init__(self, db_path: Path = DEFAULT_DB_FILE):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    priority TEXT CHECK(priority IN ('High','Medium','Low'))
                        DEFAULT 'Medium',
                    tags TEXT DEFAULT '',
                    status TEXT CHECK(status IN ('pending','completed','archived'))
                        DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                )
                """
            )
            conn.commit()

    def add_task(self, title: str, priority: str = "Medium", tags: str = "") -> int:
        """Add a new task."""
        created_at = datetime.now().isoformat()
        priority = priority.capitalize()
        if priority not in ("High", "Medium", "Low"):
            priority = "Medium"

        with self._get_connection() as conn:
            query = (
                "INSERT INTO tasks (title, priority, tags, status, created_at) "
                "VALUES (?, ?, ?, 'pending', ?)"
            )
            cursor = conn.execute(query, (title, priority, tags.strip(), created_at))
            conn.commit()
            return cursor.lastrowid or 0

    def get_tasks(
        self,
        status_filter: Optional[str] = "pending",
        tag_filter: Optional[str] = None,
        priority_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch tasks with optional filters."""
        query = "SELECT * FROM tasks WHERE 1=1"
        params: List[str] = []

        if status_filter and status_filter != "all":
            query += " AND status = ?"
            params.append(status_filter)

        if tag_filter:
            query += " AND tags LIKE ?"
            params.append(f"%{tag_filter}%")

        if priority_filter:
            query += " AND priority = ?"
            params.append(priority_filter.capitalize())

        query += (
            " ORDER BY CASE priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 "
            "WHEN 'Low' THEN 3 END, id ASC"
        )  # nosec B608

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def complete_task(self, task_id: int) -> bool:
        """Mark task as completed."""
        completed_at = datetime.now().isoformat()
        with self._get_connection() as conn:
            query = (
                "UPDATE tasks SET status = 'completed', completed_at = ? "
                "WHERE id = ?"
            )  # nosec B608
            cursor = conn.execute(query, (completed_at, task_id))
            conn.commit()
            return cursor.rowcount > 0

    def update_priority(self, task_id: int, priority: str) -> bool:
        """Update task priority level."""
        priority = priority.capitalize()
        if priority not in ("High", "Medium", "Low"):
            raise ValueError("Priority must be High, Medium, or Low")

        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE tasks SET priority = ? WHERE id = ?",
                (priority, task_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def update_tags(self, task_id: int, tags: str) -> bool:
        """Update task tags."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "UPDATE tasks SET tags = ? WHERE id = ?",
                (tags.strip(), task_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def archive_task(self, task_id: Optional[int] = None) -> int:
        """Archive task(s)."""
        with self._get_connection() as conn:
            if task_id is not None:
                cursor = conn.execute(
                    "UPDATE tasks SET status = 'archived' WHERE id = ?",
                    (task_id,),
                )
            else:
                query = (
                    "UPDATE tasks SET status = 'archived' " "WHERE status = 'completed'"
                )  # nosec B608
                cursor = conn.execute(query)
            conn.commit()
            return cursor.rowcount

    def delete_task(self, task_id: int) -> bool:
        """Permanently delete a task."""
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()
            return cursor.rowcount > 0


def format_table(tasks: List[Dict[str, Any]]) -> str:
    """Format tasks list as clean ASCII table."""
    if not tasks:
        return "No tasks found."

    headers = ["ID", "Status", "Priority", "Title", "Tags"]
    col_widths = {
        "ID": 4,
        "Status": 10,
        "Priority": 8,
        "Title": 30,
        "Tags": 15,
    }

    # Recalculate max widths based on content
    for t in tasks:
        col_widths["ID"] = max(col_widths["ID"], len(str(t["id"])))
        col_widths["Status"] = max(col_widths["Status"], len(t["status"]))
        col_widths["Priority"] = max(col_widths["Priority"], len(t["priority"]))
        col_widths["Title"] = max(col_widths["Title"], len(t["title"]))
        col_widths["Tags"] = max(col_widths["Tags"], len(t.get("tags", "") or ""))

    def line(sep: str = "+") -> str:
        parts = [sep + "-" * (col_widths[k] + 2) for k in headers]
        return "".join(parts) + sep

    def row_str(vals: List[Any]) -> str:
        parts = [f"| {str(v):<{col_widths[k]}} " for k, v in zip(headers, vals)]
        return "".join(parts) + "|"

    output = [line(), row_str(headers), line("=")]
    for t in tasks:
        icon = (
            "✔"
            if t["status"] == "completed"
            else ("📦" if t["status"] == "archived" else "⏳")
        )
        status_display = f"{icon} {t['status']}"
        row_vals = [t["id"], status_display, t["priority"], t["title"], t["tags"]]
        output.append(row_str(row_vals))
    output.append(line())

    return "\n".join(output)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Interactive TODO List Manager CLI"
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "--db", type=Path, default=DEFAULT_DB_FILE, help="SQLite DB path"
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand")

    # Add task
    add_parser = subparsers.add_parser("add", help="Add new task")
    add_parser.add_argument("title", help="Task title")
    add_parser.add_argument(
        "-p",
        "--priority",
        choices=["High", "Medium", "Low"],
        default="Medium",
    )
    add_parser.add_argument("-t", "--tags", default="", help="Comma separated tags")

    # List tasks
    list_parser = subparsers.add_parser("list", help="List tasks")
    list_parser.add_argument(
        "-s",
        "--status",
        choices=["pending", "completed", "archived", "all"],
        default="pending",
    )
    list_parser.add_argument("-t", "--tag", help="Filter by tag")
    list_parser.add_argument(
        "-p",
        "--priority",
        choices=["High", "Medium", "Low"],
        help="Filter by priority",
    )

    # Complete task
    done_parser = subparsers.add_parser("done", help="Mark task as completed")
    done_parser.add_argument("id", type=int, help="Task ID")

    # Prioritize task
    prio_parser = subparsers.add_parser("prioritize", help="Change task priority")
    prio_parser.add_argument("id", type=int, help="Task ID")
    prio_parser.add_argument(
        "priority", choices=["High", "Medium", "Low"], help="New priority"
    )

    # Tag task
    tag_parser = subparsers.add_parser("tag", help="Update task tags")
    tag_parser.add_argument("id", type=int, help="Task ID")
    tag_parser.add_argument("tags", help="Tags string")

    # Archive tasks
    arch_parser = subparsers.add_parser("archive", help="Archive task(s)")
    arch_parser.add_argument(
        "id",
        type=int,
        nargs="?",
        help="Task ID (omit to archive all completed tasks)",
    )

    # Delete task
    del_parser = subparsers.add_parser("delete", help="Delete task")
    del_parser.add_argument("id", type=int, help="Task ID")

    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entrypoint for interactive TODO list manager."""
    parser = build_parser()
    parsed = parser.parse_args(args)
    db = TodoDatabase(parsed.db)

    if parsed.command == "add":
        tid = db.add_task(parsed.title, parsed.priority, parsed.tags)
        print(f"Task #{tid} added successfully.")

    elif parsed.command == "list" or parsed.command is None:
        status = getattr(parsed, "status", "pending")
        tag = getattr(parsed, "tag", None)
        prio = getattr(parsed, "priority", None)
        tasks = db.get_tasks(status_filter=status, tag_filter=tag, priority_filter=prio)
        print(format_table(tasks))

    elif parsed.command == "done":
        if db.complete_task(parsed.id):
            print(f"Task #{parsed.id} completed! 🎉")
        else:
            print(f"Task #{parsed.id} not found.")

    elif parsed.command == "prioritize":
        if db.update_priority(parsed.id, parsed.priority):
            print(f"Task #{parsed.id} priority updated to {parsed.priority}.")
        else:
            print(f"Task #{parsed.id} not found.")

    elif parsed.command == "tag":
        if db.update_tags(parsed.id, parsed.tags):
            print(f"Task #{parsed.id} tags updated to '{parsed.tags}'.")
        else:
            print(f"Task #{parsed.id} not found.")

    elif parsed.command == "archive":
        count = db.archive_task(parsed.id)
        print(f"Archived {count} task(s).")

    elif parsed.command == "delete":
        if db.delete_task(parsed.id):
            print(f"Task #{parsed.id} deleted.")
        else:
            print(f"Task #{parsed.id} not found.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
