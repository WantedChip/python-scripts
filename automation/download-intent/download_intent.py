#!/usr/bin/env python3
"""Download Intent Classifier & Organizer.

Organizes downloaded files based on keyword contexts, calculating category
confidence scores, and supports full undo capabilities via SQLite transaction history.
"""

import argparse
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime
from typing import Any, Dict, Tuple

# Rule database for scoring
RULES: Dict[str, Dict[str, Any]] = {
    "invoices": {
        "extensions": {".pdf", ".html", ".htm"},
        "keywords": {
            "invoice": 0.5,
            "receipt": 0.5,
            "bill": 0.5,
            "statement": 0.4,
            "tax": 0.4,
            "order": 0.3,
            "payment": 0.3,
            "invoice_": 0.6,
        },
    },
    "installers": {
        "extensions": {".exe", ".msi", ".dmg", ".pkg", ".app", ".deb", ".rpm"},
        "keywords": {
            "setup": 0.5,
            "install": 0.5,
            "installer": 0.6,
            "updater": 0.4,
            "win64": 0.3,
            "x64": 0.3,
            "setup_": 0.5,
        },
    },
    "screenshots": {
        "extensions": {".png", ".jpg", ".jpeg", ".gif"},
        "keywords": {
            "screenshot": 0.8,
            "screen shot": 0.8,
            "capture": 0.6,
            "screen_shot": 0.8,
            "screenshot_": 0.8,
        },
    },
    "archives": {
        "extensions": {".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz"},
        "keywords": {"backup": 0.4, "archive": 0.4, "dump": 0.3},
    },
    "documents": {
        "extensions": {
            ".pdf",
            ".docx",
            ".xlsx",
            ".pptx",
            ".txt",
            ".csv",
            ".epub",
            ".odt",
            ".rtf",
            ".pages",
        },
        "keywords": {
            "report": 0.4,
            "guide": 0.3,
            "manual": 0.3,
            "draft": 0.3,
            "resume": 0.5,
            "cv": 0.5,
            "proposal": 0.4,
        },
    },
    "junk": {
        "extensions": {".tmp", ".crdownload", ".part", ".download", ".log"},
        "keywords": {"temp": 0.5, "tmp": 0.5, "download": 0.2},
    },
}


def init_db(db_path: str) -> None:
    """Initialize the SQLite transaction history database."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL
            )
        """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS moves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_id INTEGER NOT NULL,
                original_path TEXT NOT NULL,
                new_path TEXT NOT NULL,
                FOREIGN KEY (tx_id) REFERENCES transactions (id)
            )
        """
        )
        conn.commit()


def classify_file(filename: str) -> Tuple[str, float]:
    """Calculate confidence scores and classify a file into a category."""
    name, ext = os.path.splitext(filename.lower())
    scores: Dict[str, float] = {}

    for category, rule in RULES.items():
        score = 0.0

        # 1. Extension match base scoring
        if ext in rule["extensions"]:
            score += 0.4

        # 2. Keyword match scoring
        kw_dict: Dict[str, float] = rule["keywords"]
        for kw, weight in kw_dict.items():
            # Use regex word boundary or simple search
            if kw in name:
                score += weight

        # Cap score at 1.0
        scores[category] = min(score, 1.0)

    # Find highest scoring category
    best_cat = "uncategorized"
    best_score = 0.0

    for cat, score in scores.items():
        if score > best_score:
            best_score = score
            best_cat = cat

    # Apply minimum confidence threshold
    if best_score < 0.3:
        best_cat = "uncategorized"

    return best_cat, best_score


def move_file_recorded(
    conn: sqlite3.Connection, tx_id: int, src_path: str, dest_dir: str, category: str
) -> bool:
    """Move a file to its target category directory, logging transaction in DB."""
    # Ensure category folder exists
    cat_dir = os.path.join(dest_dir, category)
    os.makedirs(cat_dir, exist_ok=True)

    filename = os.path.basename(src_path)
    dest_path = os.path.join(cat_dir, filename)

    # Handle collisions by appending timestamps
    if os.path.exists(dest_path):
        name, ext = os.path.splitext(filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_path = os.path.join(cat_dir, f"{name}_{timestamp}{ext}")

    try:
        shutil.move(src_path, dest_path)
        # Log to database
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO moves (tx_id, original_path, new_path) VALUES (?, ?, ?)",
            (tx_id, os.path.abspath(src_path), os.path.abspath(dest_path)),
        )
        conn.commit()
        return True
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Failed to move {filename}: {e}", file=sys.stderr)
        return False


# pylint: disable=too-many-locals,too-many-branches
def run_scan(watch_dir: str, dest_dir: str, db_path: str, dry_run: bool) -> None:
    """Scan and organize downloads directory."""
    if not os.path.exists(watch_dir):
        print(f"Watch directory does not exist: {watch_dir}", file=sys.stderr)
        sys.exit(1)

    init_db(db_path)
    conn = sqlite3.connect(db_path)

    # Get items in watch directory
    files_to_process = []
    for f in os.listdir(watch_dir):
        full_path = os.path.join(watch_dir, f)
        if os.path.isfile(full_path):
            files_to_process.append(full_path)

    if not files_to_process:
        print("No files to organize in watch directory.")
        conn.close()
        return

    # Create transaction
    tx_id = 0
    if not dry_run:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO transactions (timestamp) VALUES (?)",
            (datetime.now().isoformat(),),
        )
        last_id = cursor.lastrowid
        tx_id = last_id if last_id is not None else 0
        conn.commit()

    print(f"Scanning downloads in {watch_dir}...")
    moved_count = 0

    for file_path in files_to_process:
        filename = os.path.basename(file_path)
        # Skip temporary downloader lock/part files immediately
        if filename.endswith((".tmp", ".crdownload", ".part", ".download")):
            continue

        category, confidence = classify_file(filename)

        if category == "uncategorized":
            continue

        if dry_run:
            print(
                f"[DRY-RUN] Move '{filename}' -> category '{category}' "
                f"(Confidence: {confidence:.2f})"
            )
        else:
            success = move_file_recorded(conn, tx_id, file_path, dest_dir, category)
            if success:
                print(
                    f"Organized: '{filename}' -> {category}/ "
                    f"(Confidence: {confidence:.2f})"
                )
                moved_count += 1

    if not dry_run:
        # Check if we actually moved anything; if not, delete the empty transaction
        cursor = conn.cursor()
        if moved_count == 0:
            cursor.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
            conn.commit()
            print("No files met organizing confidence threshold. 0 files moved.")
        else:
            print(
                f"Successfully organized {moved_count} files (Transaction ID: {tx_id})."
            )

    conn.close()


def run_undo(db_path: str) -> None:
    """Roll back the last transaction in the history database."""
    if not os.path.exists(db_path):
        print("No transaction database found. Nothing to undo.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get last transaction
    cursor.execute("SELECT id, timestamp FROM transactions ORDER BY id DESC LIMIT 1")
    tx = cursor.fetchone()
    if not tx:
        print("No transactions found in history database. Nothing to undo.")
        conn.close()
        return

    tx_id, timestamp = tx
    print(f"Undoing transaction {tx_id} (recorded at {timestamp})...")

    # Get moves in transaction
    cursor.execute(
        "SELECT original_path, new_path FROM moves WHERE tx_id = ?", (tx_id,)
    )
    moves = cursor.fetchall()

    rollback_count = 0
    for original, current in moves:
        if not os.path.exists(current):
            print(
                f"Warning: File no longer exists at organized path: {current}. "
                "Skipping."
            )
            continue

        # Ensure original directory exists
        orig_dir = os.path.dirname(original)
        os.makedirs(orig_dir, exist_ok=True)

        try:
            shutil.move(current, original)
            print(f"Restored: {os.path.basename(original)} -> {orig_dir}")
            rollback_count += 1
        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"Error restoring file to {original}: {e}", file=sys.stderr)

    # Clean up transaction
    cursor.execute("DELETE FROM moves WHERE tx_id = ?", (tx_id,))
    cursor.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    conn.commit()
    conn.close()

    print(f"Rollback completed. Restored {rollback_count}/{len(moves)} files.")


def run_watch(watch_dir: str, dest_dir: str, db_path: str, interval: int) -> None:
    """Continuously poll watch folder for new files and organize them."""
    print(f"Starting directory watcher on {watch_dir} (interval: {interval}s)...")
    print("Press Ctrl+C to stop watching.")
    try:
        while True:
            # Run scan periodically
            run_scan(watch_dir, dest_dir, db_path, dry_run=False)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nWatcher stopped.")
        sys.exit(0)


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Organize downloads folder based on filename contextual intent with "
            "SQLite undo capabilities."
        )
    )

    subparsers = parser.add_subparsers(
        dest="command", required=True, help="Subcommands"
    )

    # Scan parser
    scan_parser = subparsers.add_parser(
        "scan", help="Scan and organize target downloads directory."
    )
    scan_parser.add_argument(
        "-w", "--watch-dir", required=True, help="Folder containing downloads to scan."
    )
    scan_parser.add_argument(
        "-d",
        "--dest-dir",
        required=True,
        help="Folder where organized categories will be placed.",
    )
    scan_parser.add_argument(
        "--dry-run", action="store_true", help="Preview moves without moving files."
    )

    # Watch parser
    watch_parser = subparsers.add_parser(
        "watch", help="Continuously watch folder for new downloads."
    )
    watch_parser.add_argument(
        "-w", "--watch-dir", required=True, help="Downloads directory to watch."
    )
    watch_parser.add_argument(
        "-d",
        "--dest-dir",
        required=True,
        help="Organized categories destination folder.",
    )
    watch_parser.add_argument(
        "-i",
        "--interval",
        type=int,
        default=5,
        help="Polling scan interval in seconds (default: 5).",
    )

    # Undo parser
    subparsers.add_parser(
        "undo", help="Roll back the last organizing transaction operation."
    )

    args = parser.parse_args()

    db_path = os.path.join(os.path.expanduser("~"), ".download_intent_history.db")

    if args.command == "scan":
        run_scan(args.watch_dir, args.dest_dir, db_path, args.dry_run)
    elif args.command == "watch":
        run_watch(args.watch_dir, args.dest_dir, db_path, args.interval)
    elif args.command == "undo":
        run_undo(db_path)


if __name__ == "__main__":
    main()
