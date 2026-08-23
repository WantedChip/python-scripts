"""Screenshot Index & Search Tool.

Indexes screenshots locally using OCR and SQLite, allowing users to search
their screenshot history by keyword, app name, creation date range, or topic.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import datetime
import os
import sqlite3
import sys
from dataclasses import dataclass
from typing import List, Optional

PYTESSERACT_AVAILABLE = True
try:
    import pytesseract
    from PIL import Image
except ImportError:
    PYTESSERACT_AVAILABLE = False


@dataclass
class ScreenshotRecord:
    """Dataclass representing a stored screenshot record."""

    id: Optional[int]
    filepath: str
    app_name: str
    text_content: str
    created_at: str  # ISO Format YYYY-MM-DD
    topic: str


class ScreenshotIndexer:
    """Manages SQLite DB storage and search operations for OCR'd screenshots."""

    def __init__(self, db_path: str = "screenshots.db") -> None:
        """Initialize database connection and schema.

        Args:
            db_path: Path to SQLite database file or ':memory:' for tests.
        """
        self.db_path = db_path
        self.conn: sqlite3.Connection = sqlite3.connect(self.db_path)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        """Helper to get the shared database connection."""
        return self.conn

    def init_db(self) -> None:
        """Creates sqlite database schema if it doesn't already exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS screenshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filepath TEXT UNIQUE NOT NULL,
                    app_name TEXT NOT NULL,
                    text_content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    topic TEXT NOT NULL
                )
            """
            )
            conn.commit()

    def extract_text_from_image(
        self, image_path: str, mock_text: Optional[str] = None
    ) -> str:
        """Runs OCR on the target image to extract text.

        Args:
            image_path: Path to image file.
            mock_text: Optional text to return in mock mode.

        Returns:
            Extracted text string.
        """
        if mock_text is not None:
            return mock_text

        if not PYTESSERACT_AVAILABLE:
            return f"Mock OCR content for {os.path.basename(image_path)}"

        try:
            img = Image.open(image_path)
            raw = str(pytesseract.image_to_string(img))
            return " ".join(raw.strip().split())
        except Exception:  # pylint: disable=broad-exception-caught
            return ""

    def add_screenshot(
        self,
        filepath: str,
        app_name: str = "Unknown",
        topic: str = "General",
        created_at: Optional[str] = None,
        mock_text: Optional[str] = None,
    ) -> int:
        """Indexes a screenshot into the database.

        Args:
            filepath: Path to screenshot file.
            app_name: Application name associated with the screenshot.
            topic: Broad topic or tag.
            created_at: Date string (YYYY-MM-DD). Defaults to current date.
            mock_text: Predefined OCR text for testing/mocking.

        Returns:
            ID of the inserted database record.
        """
        abs_path = os.path.abspath(filepath)
        text = self.extract_text_from_image(filepath, mock_text=mock_text)
        date_str = created_at or datetime.date.today().isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = (
                "INSERT OR REPLACE INTO screenshots (filepath, app_name,"
                " text_content, created_at, topic) VALUES (?, ?, ?, ?, ?)"
            )
            cursor.execute(query, (abs_path, app_name, text, date_str, topic))
            conn.commit()
            return cursor.lastrowid or 0

    def search(
        self,
        keyword: Optional[str] = None,
        app_name: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        topic: Optional[str] = None,
    ) -> List[ScreenshotRecord]:
        """Searches indexed screenshots using multiple optional criteria.

        Args:
            keyword: Substring match in OCR text content.
            app_name: Filter by application name.
            start_date: Filter screenshots on or after YYYY-MM-DD.
            end_date: Filter screenshots on or before YYYY-MM-DD.
            topic: Filter by topic tag.

        Returns:
            List of matching ScreenshotRecord objects.
        """
        query = (
            "SELECT id, filepath, app_name, text_content, created_at, topic"
            " FROM screenshots WHERE 1=1"
        )
        params: List[str] = []

        if keyword:
            query += " AND text_content LIKE ?"
            params.append(f"%{keyword}%")
        if app_name:
            query += " AND LOWER(app_name) = LOWER(?)"
            params.append(app_name)
        if topic:
            query += " AND LOWER(topic) = LOWER(?)"
            params.append(topic)
        if start_date:
            query += " AND created_at >= ?"
            params.append(start_date)
        if end_date:
            query += " AND created_at <= ?"
            params.append(end_date)

        results: List[ScreenshotRecord] = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            for row in rows:
                results.append(
                    ScreenshotRecord(
                        id=row[0],
                        filepath=row[1],
                        app_name=row[2],
                        text_content=row[3],
                        created_at=row[4],
                        topic=row[5],
                    )
                )
        return results


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Index and search local screenshots with OCR."
    parser = argparse.ArgumentParser(description=desc)
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # Index command
    index_parser = subparsers.add_parser("index", help="Index a screenshot")
    index_parser.add_argument(
        "--file",
        type=str,
        required=True,
        help="Screenshot image file path",
    )
    index_parser.add_argument(
        "--app", type=str, default="Unknown", help="Name of application"
    )
    index_parser.add_argument(
        "--topic", type=str, default="General", help="Topic or category tag"
    )
    index_parser.add_argument("--date", type=str, help="Date in YYYY-MM-DD format")
    index_parser.add_argument("--mock-text", type=str, help="Mock OCR text for testing")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search screenshot database")
    search_parser.add_argument(
        "--query", type=str, help="Keyword query to search in OCR text"
    )
    search_parser.add_argument("--app", type=str, help="Filter by app name")
    search_parser.add_argument("--topic", type=str, help="Filter by topic")
    search_parser.add_argument("--start-date", type=str, help="Start date YYYY-MM-DD")
    search_parser.add_argument("--end-date", type=str, help="End date YYYY-MM-DD")

    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI interface for indexing and searching screenshots."""
    parser = build_parser()
    parsed = parser.parse_args(args)
    indexer = ScreenshotIndexer()

    if parsed.command == "index":
        rec_id = indexer.add_screenshot(
            filepath=parsed.file,
            app_name=parsed.app,
            topic=parsed.topic,
            created_at=parsed.date,
            mock_text=parsed.mock_text,
        )
        print(f"Indexed screenshot #{rec_id}: {parsed.file}")
    elif parsed.command == "search":
        matches = indexer.search(
            keyword=parsed.query,
            app_name=parsed.app,
            start_date=parsed.start_date,
            end_date=parsed.end_date,
            topic=parsed.topic,
        )
        print(f"Found {len(matches)} matching screenshot(s):")
        for match in matches:
            snippet = f"{match.text_content[:60]}..."
            print(
                f"- [{match.created_at}] [{match.app_name}] {match.filepath} |"
                f" Content snippet: '{snippet}'"
            )
    else:
        parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())
