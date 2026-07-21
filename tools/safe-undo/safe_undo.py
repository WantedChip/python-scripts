#!/usr/bin/env python3
"""Safe Undo.

Provides library APIs (move, rename, delete) and a CLI wrapper supporting
destructive file operations by logging transactions to SQLite and backup zips,
enabling full rollback capabilities.
"""

import argparse
import os
import shutil
import sqlite3
import sys
import zipfile
from datetime import datetime
from typing import Optional, Tuple


def init_db(db_path: str) -> None:
    """Initialize the safe undo transactions database schema."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                action TEXT NOT NULL,
                src_path TEXT NOT NULL,
                dest_path TEXT,
                quarantine_path TEXT NOT NULL,
                is_directory INTEGER NOT NULL
            )
        """
        )
        conn.commit()


def backup_to_quarantine(src_path: str, quarantine_dir: str) -> Tuple[str, bool]:
    """Compress and copy target file/directory to quarantine."""
    is_dir = os.path.isdir(src_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    base_name = os.path.basename(src_path)
    zip_name = f"{base_name}_{timestamp}.zip"
    zip_path = os.path.join(quarantine_dir, zip_name)

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            if is_dir:
                for root, _, files in os.walk(src_path):
                    for file in files:
                        full_fpath = os.path.join(root, file)
                        rel_path = os.path.relpath(
                            full_fpath, os.path.dirname(src_path)
                        )
                        zipf.write(full_fpath, rel_path)
            else:
                zipf.write(src_path, base_name)
        return zip_path, is_dir
    except (OSError, zipfile.BadZipFile) as e:
        if os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except OSError:
                pass
        raise OSError(f"Failed to create quarantine zip backup: {e}") from e


# pylint: disable=too-many-arguments,too-many-positional-arguments
def log_transaction(
    db_path: str,
    action: str,
    src_path: str,
    dest_path: Optional[str],
    quarantine_path: str,
    is_dir: bool,
) -> int:
    """Insert a new transaction log entry in the database."""
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            query = (
                "INSERT INTO transactions "
                "(timestamp, action, src_path, dest_path, quarantine_path, "
                "is_directory) VALUES (?, ?, ?, ?, ?, ?)"
            )
            cursor.execute(
                query,
                (
                    datetime.now().isoformat(),
                    action,
                    src_path,
                    dest_path,
                    quarantine_path,
                    1 if is_dir else 0,
                ),
            )
            tx_id = cursor.lastrowid
            conn.commit()
            return tx_id if tx_id else -1
    except sqlite3.Error as e:
        print(f"Warning: Failed to log transaction in database: {e}", file=sys.stderr)
        return -1


def safe_delete(path: str, db_path: str, quarantine_dir: str) -> bool:
    """Safely back up and delete a target file/folder."""
    abs_src = os.path.abspath(path)
    if not os.path.exists(abs_src):
        return False

    try:
        q_path, is_dir = backup_to_quarantine(abs_src, quarantine_dir)
        tx_id = log_transaction(db_path, "delete", abs_src, None, q_path, is_dir)

        if is_dir:
            shutil.rmtree(abs_src)
        else:
            os.remove(abs_src)

        print(f"[TX:{tx_id}] Quarantined & Deleted: '{abs_src}'")
        return True
    except (OSError, zipfile.BadZipFile) as e:
        print(f"Error: Safe delete failed: {e}", file=sys.stderr)
        return False


def safe_move(src: str, dest: str, db_path: str, quarantine_dir: str) -> bool:
    """Safely back up and move a file/folder to a new destination."""
    abs_src = os.path.abspath(src)
    abs_dest = os.path.abspath(dest)
    if not os.path.exists(abs_src):
        return False

    try:
        q_path, is_dir = backup_to_quarantine(abs_src, quarantine_dir)
        tx_id = log_transaction(db_path, "move", abs_src, abs_dest, q_path, is_dir)

        os.makedirs(os.path.dirname(abs_dest), exist_ok=True)
        shutil.move(abs_src, abs_dest)

        print(f"[TX:{tx_id}] Quarantined & Moved: '{abs_src}' -> '{abs_dest}'")
        return True
    except (OSError, zipfile.BadZipFile) as e:
        print(f"Error: Safe move failed: {e}", file=sys.stderr)
        return False


# pylint: disable=too-many-return-statements,too-many-branches,too-many-statements
def rollback_transaction(tx_id: int, db_path: str) -> bool:
    """Rollback a destructive operation by unpacking backups and updating logs."""
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            query = (
                "SELECT id, action, src_path, dest_path, quarantine_path, "
                "is_directory FROM transactions WHERE id = ?"
            )
            cursor.execute(query, (tx_id,))
            row = cursor.fetchone()
    except sqlite3.Error as e:
        print(f"Database error: {e}", file=sys.stderr)
        return False

    if not row:
        print(f"Error: No transaction found matching ID: {tx_id}", file=sys.stderr)
        return False

    t_id, action, src_path, dest_path, q_path, _ = row

    if not os.path.exists(q_path):
        print(f"Error: Quarantine ZIP backup file missing: {q_path}", file=sys.stderr)
        return False

    if action == "delete":
        if os.path.exists(src_path):
            print(
                f"Error: A file already exists at original location: {src_path}",
                file=sys.stderr,
            )
            return False

        try:
            print(f"Restoring '{src_path}'...")
            parent_dir = os.path.dirname(src_path)
            os.makedirs(parent_dir, exist_ok=True)
            with zipfile.ZipFile(q_path, "r") as zipf:
                zipf.extractall(parent_dir)
        except (OSError, zipfile.BadZipFile) as e:
            print(f"Error extracting backup: {e}", file=sys.stderr)
            return False

    elif action in ("move", "rename"):
        if dest_path and not os.path.exists(dest_path):
            msg = (
                f"Warning: Moved item not found at destination '{dest_path}'. "
                "Standard restoration from backup."
            )
            print(msg)
        elif dest_path:
            try:
                if os.path.isdir(dest_path):
                    shutil.rmtree(dest_path)
                else:
                    os.remove(dest_path)
            except OSError:
                pass

        if os.path.exists(src_path):
            print(
                f"Error: A file already exists at source location: {src_path}",
                file=sys.stderr,
            )
            return False

        try:
            print(f"Restoring '{src_path}'...")
            parent_dir = os.path.dirname(src_path)
            os.makedirs(parent_dir, exist_ok=True)
            with zipfile.ZipFile(q_path, "r") as zipf:
                zipf.extractall(parent_dir)
        except (OSError, zipfile.BadZipFile) as e:
            print(f"Error extracting backup: {e}", file=sys.stderr)
            return False

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM transactions WHERE id = ?", (t_id,))
            conn.commit()
        os.remove(q_path)
        print(f"[+] Rollback of transaction {t_id} completed successfully.")
        return True
    except (OSError, sqlite3.Error) as e:
        print(f"Warning: Cleanup failed after rollback: {e}", file=sys.stderr)
        return True


def run_list(db_path: str) -> None:
    """Print a list of safe undo transaction histories."""
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            query = (
                "SELECT id, timestamp, action, src_path, dest_path FROM "
                "transactions ORDER BY id DESC"
            )
            cursor.execute(query)
            rows = cursor.fetchall()
    except sqlite3.Error as e:
        print(f"Database error: {e}", file=sys.stderr)
        return

    if not rows:
        print("No transactions logged in Safe Undo history.")
        return

    print("========================================================================")
    print("SAFE UNDO: FILESYSTEM TRANSACTIONS LOG")
    print("========================================================================")
    print(f"{'TX_ID':<5} | {'TIMESTAMP':<19} | {'ACTION':<7} | {'DETAILS'}")
    print("-" * 80)
    for t_id, time_str, action, src, dest in rows:
        clean_time = time_str[:19].replace("T", " ")
        detail = src
        if dest:
            detail = f"{src} -> {dest}"
        if len(detail) > 42:
            detail = detail[:39] + "..."
        print(f"{t_id:<5} | {clean_time:<19} | {action:<7} | {detail}")
    print("=" * 80)
    print("To roll back: python safe_undo.py rollback <tx_id>")
    print("=" * 80)


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Destructive filesystem actions wrapper library supporting rollbacks."
        )
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute.")

    subparsers.add_parser("list", help="List all logged safe-undo transactions.")

    rollback_parser = subparsers.add_parser(
        "rollback", help="Roll back/undo a filesystem operation."
    )
    rollback_parser.add_argument(
        "tx_id", type=int, help="Transaction ID number to revert."
    )

    delete_parser = subparsers.add_parser(
        "delete", help="Safely delete target file/folder."
    )
    delete_parser.add_argument("path", help="Path to delete.")

    move_parser = subparsers.add_parser("move", help="Safely move file/folder.")
    move_parser.add_argument("src", help="Source file.")
    move_parser.add_argument("dest", help="Destination file.")

    args = parser.parse_args()

    home = os.path.expanduser("~")
    quarantine_dir = os.path.join(home, ".safe_undo_quarantine")
    os.makedirs(quarantine_dir, exist_ok=True)
    db_path = os.path.join(quarantine_dir, ".safe_undo_manifest.db")
    init_db(db_path)

    if args.command == "list":
        run_list(db_path)
    elif args.command == "rollback":
        rollback_transaction(args.tx_id, db_path)
    elif args.command == "delete":
        safe_delete(args.path, db_path, quarantine_dir)
    elif args.command == "move":
        safe_move(args.src, args.dest, db_path, quarantine_dir)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
