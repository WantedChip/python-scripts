#!/usr/bin/env python3
"""Archive Before Delete.

Quarantines files/folders before deletion and tracks them in an SQLite manifest
database to allow easy, safe recovery.
"""

import argparse
import os
import shutil
import sqlite3
import sys
import zipfile
from datetime import datetime


def init_db(db_path: str) -> None:
    """Initialize the manifest database."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS quarantine (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_path TEXT NOT NULL,
                archive_name TEXT NOT NULL,
                deleted_at TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                is_directory INTEGER NOT NULL
            )
        """
        )
        conn.commit()


def get_dir_size(path: str) -> int:
    """Calculate total size of a directory in bytes."""
    total = 0
    try:
        for dirpath, _, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.exists(fp) and not os.path.islink(fp):
                    total += os.path.getsize(fp)
    except OSError:
        pass
    return total


# pylint: disable=too-many-locals,too-many-branches,too-many-statements
def quarantine_path(path: str, quarantine_dir: str, db_path: str, force: bool) -> bool:
    """Archive and delete a single file or directory."""
    if not os.path.exists(path):
        print(f"Error: Path does not exist: {path}", file=sys.stderr)
        return False

    abs_path = os.path.abspath(path)
    is_dir = os.path.isdir(abs_path)

    # Ask for confirmation unless forced
    if not force:
        confirm = (
            input(f"Are you sure you want to delete '{abs_path}'? [y/N]: ")
            .strip()
            .lower()
        )
        if confirm not in ("y", "yes"):
            print(f"Skipped: {abs_path}")
            return False

    # Get size
    if is_dir:
        size = get_dir_size(abs_path)
    else:
        try:
            size = os.path.getsize(abs_path)
        except OSError:
            size = 0

    # Create unique archive name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = os.path.basename(abs_path)
    archive_name = f"{base_name}_{timestamp}.zip"
    archive_path = os.path.join(quarantine_dir, archive_name)

    # Perform compression
    try:
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            if is_dir:
                # Walk and add all files
                for root, _, files in os.walk(abs_path):
                    for file in files:
                        full_fpath = os.path.join(root, file)
                        rel_path = os.path.relpath(
                            full_fpath, os.path.dirname(abs_path)
                        )
                        zipf.write(full_fpath, rel_path)
            else:
                zipf.write(abs_path, base_name)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error: Failed to create quarantine archive: {e}", file=sys.stderr)
        if os.path.exists(archive_path):
            try:
                os.remove(archive_path)
            except OSError:
                pass
        return False

    # Log to DB
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        insert_sql = (
            "INSERT INTO quarantine (original_path, archive_name, deleted_at, "
            "size_bytes, is_directory) VALUES (?, ?, ?, ?, ?)"
        )
        cursor.execute(
            insert_sql,
            (
                abs_path,
                archive_name,
                datetime.now().isoformat(),
                size,
                1 if is_dir else 0,
            ),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        print(
            f"Warning: Failed to log transaction in SQLite database: {e}",
            file=sys.stderr,
        )

    # Perform deletion
    try:
        if is_dir:
            shutil.rmtree(abs_path)
        else:
            os.remove(abs_path)
        print(f"Successfully quarantined & deleted: '{abs_path}' -> {archive_name}")
        return True
    except (OSError, ValueError) as e:
        print(
            f"Error: Archive created but failed to delete original path: {e}",
            file=sys.stderr,
        )
        # Attempt to roll back archive
        try:
            os.remove(archive_path)
        except OSError:
            pass
        return False


def run_list(db_path: str) -> None:
    """List all quarantined files/folders."""
    if not os.path.exists(db_path):
        print("No quarantine history found.")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        query_sql = (
            "SELECT id, original_path, archive_name, deleted_at, size_bytes "
            "FROM quarantine ORDER BY id DESC"
        )
        cursor.execute(query_sql)
        rows = cursor.fetchall()
        conn.close()
    except sqlite3.Error as e:
        print(f"Database error: {e}", file=sys.stderr)
        return

    if not rows:
        print("Quarantine is empty.")
        return

    print("========================================================================")
    print(f"{'ID':<4} | {'Deleted At':<19} | {'Size (KB)':<10} | {'Original Path'}")
    print("========================================================================")
    for q_id, path, _, date_str, size in rows:
        try:
            date_clean = datetime.fromisoformat(date_str).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            date_clean = date_str[:19]
        size_kb = f"{size / 1024.0:.1f}"

        display_path = path
        if len(display_path) > 40:
            display_path = "..." + display_path[-37:]

        print(f"{q_id:<4} | {date_clean:<19} | {size_kb:<10} | {display_path}")


def run_restore(target: str, quarantine_dir: str, db_path: str) -> None:
    """Restore a quarantined file/folder using its ID or original path."""
    if not os.path.exists(db_path):
        print("Error: No quarantine manifest database found.", file=sys.stderr)
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        if target.isdigit():
            id_query = (
                "SELECT id, original_path, archive_name, is_directory FROM "
                "quarantine WHERE id = ?"
            )
            cursor.execute(id_query, (int(target),))
        else:
            path_query = (
                "SELECT id, original_path, archive_name, is_directory FROM "
                "quarantine WHERE original_path = ?"
            )
            cursor.execute(path_query, (os.path.abspath(target),))

        row = cursor.fetchone()
    except sqlite3.Error as e:
        print(f"Database error: {e}", file=sys.stderr)
        return

    if not row:
        print(
            f"Error: No matching quarantine record found for: '{target}'",
            file=sys.stderr,
        )
        if hasattr(conn, "close"):
            conn.close()
        return

    q_id, orig_path, archive_name, _ = row
    archive_path = os.path.join(quarantine_dir, archive_name)

    if not os.path.exists(archive_path):
        print(
            f"Error: Archive ZIP file not found in quarantine: {archive_path}",
            file=sys.stderr,
        )
        conn.close()
        return

    if os.path.exists(orig_path):
        msg = (
            "Error: A file or directory already exists at target restore path: "
            f"{orig_path}"
        )
        print(msg, file=sys.stderr)
        conn.close()
        return

    parent_dir = os.path.dirname(orig_path)
    os.makedirs(parent_dir, exist_ok=True)

    try:
        print(f"Restoring '{orig_path}' from {archive_name}...")
        with zipfile.ZipFile(archive_path, "r") as zipf:
            zipf.extractall(parent_dir)

        cursor.execute("DELETE FROM quarantine WHERE id = ?", (q_id,))
        conn.commit()
        conn.close()

        os.remove(archive_path)
        print("Restoration completed successfully.")
    except (zipfile.BadZipFile, OSError, ValueError) as e:
        print(f"Error: Restoration failed: {e}", file=sys.stderr)


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Wrap dangerous deletion commands by creating a quarantine archive "
            "and manifest database."
        )
    )

    parser.add_argument("paths", nargs="*", help="Files or folders to delete safely.")
    parser.add_argument(
        "-l", "--list", action="store_true", help="List all files in the quarantine."
    )
    parser.add_argument(
        "-r", "--restore", help="Restore a deleted item by its ID or original path."
    )
    parser.add_argument(
        "-q",
        "--quarantine-dir",
        help="Custom quarantine directory (default: ~/.trash_archive).",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force delete without interactive confirmation.",
    )

    args = parser.parse_args()

    quar_dir = args.quarantine_dir
    if not quar_dir:
        quar_dir = os.path.join(os.path.expanduser("~"), ".trash_archive")

    os.makedirs(quar_dir, exist_ok=True)
    db_path = os.path.join(quar_dir, ".quarantine_manifest.db")
    init_db(db_path)

    if args.list:
        run_list(db_path)
    elif args.restore:
        run_restore(args.restore, quar_dir, db_path)
    elif args.paths:
        success_count = 0
        for p in args.paths:
            if quarantine_path(p, quar_dir, db_path, args.force):
                success_count += 1
        print(f"Quarantined {success_count}/{len(args.paths)} targets.")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
