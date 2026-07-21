#!/usr/bin/env python3
"""Screenshot Search.

OCRs local screenshot files recursively, index them into an SQLite database,
and supports fast full-text queries for matching images.
"""

import argparse
import os
import shutil
import sqlite3
import sys
from typing import Tuple

# Optional Pillow and pytesseract imports
try:
    import pytesseract
    from PIL import Image

    HAS_LIBS = True
except ImportError:
    HAS_LIBS = False


def init_db(db_path: str) -> None:
    """Initialize the search database schema."""
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS screenshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                last_modified REAL NOT NULL,
                ocr_text TEXT NOT NULL
            )
        """
        )
        conn.commit()


def get_default_screenshots_dir() -> str:
    """Guess the default user pictures/screenshots directory."""
    user_home = os.path.expanduser("~")
    windows_path = os.path.join(user_home, "Pictures", "Screenshots")
    if os.path.exists(windows_path):
        return windows_path

    generic_pictures = os.path.join(user_home, "Pictures")
    if os.path.exists(generic_pictures):
        return generic_pictures

    return "."


def ocr_image(image_path: str) -> str:
    """Run OCR on the image path returning extracted text."""
    if not HAS_LIBS:
        return ""
    try:
        if not shutil.which("tesseract"):
            tess_win_paths = [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            ]
            for tp in tess_win_paths:
                if os.path.exists(tp):
                    pytesseract.pytesseract.tesseract_cmd = tp
                    break
            else:
                return "[Warning: Tesseract binary not found on PATH or Program Files]"

        with Image.open(image_path) as img:
            text: str = pytesseract.image_to_string(img)
            return text.strip()
    except (OSError, pytesseract.TesseractError) as e:
        return f"[Error performing OCR: {e}]"


# pylint: disable=too-many-locals
def run_indexing(scan_dir: str, db_path: str) -> Tuple[int, int]:
    """Scan directory recursively, running OCR on new/modified images."""
    if not HAS_LIBS:
        print(
            "Error: Required libraries (Pillow, pytesseract) are not installed.\n"
            "Please run: pip install Pillow pytesseract\n"
            "And ensure the Tesseract OCR engine binary is installed on your system.",
            file=sys.stderr,
        )
        return 0, 0

    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT path, last_modified FROM screenshots")
    db_records = {row[0]: row[1] for row in cursor.fetchall()}

    supported_extensions = (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp")
    new_count = 0
    updated_count = 0

    print(f"Scanning '{scan_dir}' for screenshots...")

    for root, _, files in os.walk(scan_dir):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in supported_extensions:
                continue

            full_path = os.path.abspath(os.path.join(root, f))
            try:
                mtime = os.path.getmtime(full_path)
            except OSError:
                continue

            if full_path in db_records:
                if mtime == db_records[full_path]:
                    continue
                updated_count += 1
            else:
                new_count += 1

            print(f"Indexing: {os.path.basename(full_path)}")
            text = ocr_image(full_path)

            try:
                query = (
                    "INSERT OR REPLACE INTO screenshots "
                    "(path, last_modified, ocr_text) VALUES (?, ?, ?)"
                )
                cursor.execute(query, (full_path, mtime, text))
                conn.commit()
            except sqlite3.Error as e:
                print(f"Database error saving {full_path}: {e}", file=sys.stderr)

    conn.close()
    return new_count, updated_count


def run_search(query: str, db_path: str) -> None:
    """Query the indexed screenshots for search matches."""
    if not os.path.exists(db_path):
        print(
            "Error: No search index database found. Please run index scan first.",
            file=sys.stderr,
        )
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    sql_query = "SELECT path, ocr_text FROM screenshots WHERE ocr_text LIKE ?"
    pattern = f"%{query}%"

    try:
        cursor.execute(sql_query, (pattern,))
        rows = cursor.fetchall()
    except sqlite3.Error as e:
        print(f"Database error running search: {e}", file=sys.stderr)
        conn.close()
        return

    conn.close()

    if not rows:
        print(f"No screenshots found matching: '{query}'")
        return

    print("========================================================================")
    print(f"SCREENSHOT SEARCH RESULTS FOR: '{query}' ({len(rows)} matches)")
    print("========================================================================")

    for idx, row in enumerate(rows, 1):
        path = row["path"]
        text = row["ocr_text"]

        matched_snippet = ""
        lines = text.split("\n")
        for line in lines:
            if query.lower() in line.lower():
                matched_snippet = line.strip()
                if len(matched_snippet) > 70:
                    matched_snippet = matched_snippet[:67] + "..."
                break

        print(f"{idx}. File: {os.path.basename(path)}")
        print(f"   Path:    {path}")
        if matched_snippet:
            print(f"   Context: ... {matched_snippet} ...")
        print("-" * 80)


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description="OCR a screenshot folder locally and search text content."
    )

    parser.add_argument(
        "query", nargs="?", help="Text keyword to search in screenshots index."
    )
    parser.add_argument(
        "-s",
        "--scan-dir",
        help=(
            "Custom folder path to scan recursively for images "
            "(default: Pictures/Screenshots)."
        ),
    )
    parser.add_argument(
        "-i",
        "--index-only",
        action="store_true",
        help="Only run directory scanning and indexer loop without performing search.",
    )
    parser.add_argument(
        "--db-path", help="Custom SQLite search database destination path."
    )

    args = parser.parse_args()

    scan_dir = args.scan_dir
    if not scan_dir:
        scan_dir = get_default_screenshots_dir()

    db_path = args.db_path
    if not db_path:
        db_path = os.path.join(os.path.expanduser("~"), ".screenshot_search_index.db")

    if args.index_only or not args.query:
        if not HAS_LIBS:
            msg = (
                "Error: Missing Pillow or pytesseract packages. "
                "Install them to index files."
            )
            print(msg, file=sys.stderr)
            sys.exit(1)
        new_cnt, up_cnt = run_indexing(scan_dir, db_path)
        print(f"Indexing completed: {new_cnt} new files indexed, {up_cnt} updated.")

    if args.query:
        if HAS_LIBS:
            run_indexing(scan_dir, db_path)
        else:
            msg = (
                "Warning: Missing indexing libraries. "
                "Searching cached index database only."
            )
            print(msg)
        run_search(args.query, db_path)


if __name__ == "__main__":
    main()
