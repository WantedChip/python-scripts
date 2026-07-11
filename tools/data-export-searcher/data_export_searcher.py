"""Personal Data Export Searcher.

A CLI tool to search through locally exported personal data archives
(JSON chat logs, CSV, MBOX, HTML exports) with advanced query filters.
"""

import argparse
import csv
import datetime
import html.parser
import json
import logging
import mailbox
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Generator, List, Optional

# pylint: disable=duplicate-code

logger = logging.getLogger("data_export_searcher")


@dataclass
class SearchResult:
    """Represents a matched message or entry in the search."""

    source_file: str
    format: str
    timestamp: Optional[str]
    sender: Optional[str]
    subject: Optional[str]
    content: str


class SimpleHTMLTextExtractor(html.parser.HTMLParser):
    """HTML parser to extract text and title from HTML files."""

    def __init__(self) -> None:
        super().__init__()
        self.text_parts: List[str] = []
        self.title: Optional[str] = None
        self.in_title: bool = False
        # Whitelist override methods for vulture
        _ = (self.handle_starttag, self.handle_endtag, self.handle_data)

    def handle_starttag(self, tag: str, _attrs: Any) -> None:
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        clean_data = data.strip()
        if clean_data:
            if self.in_title:
                self.title = clean_data
            else:
                self.text_parts.append(clean_data)

    def get_text(self) -> str:
        """Return the extracted clean text."""
        return "\n".join(self.text_parts)


def setup_logging(verbose: bool) -> None:
    """Configure logging to stdout."""
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.setLevel(level)
    logger.addHandler(handler)
    logging.basicConfig(level=logging.WARNING, handlers=[handler])


def parse_date(date_str: str) -> Optional[datetime.datetime]:
    """Parse dates of common formats into a datetime object.

    Args:
        date_str: Input date string.

    Returns:
        datetime object or None.
    """
    # pylint: disable=too-many-return-statements, too-many-branches
    cleaned = date_str.strip()

    # Remove timezone offset strings like +00:00 or Z
    cleaned = re.sub(r"(?:\+|-)\d{2}:?\d{2}$", "", cleaned)
    cleaned = re.sub(r"Z$", "", cleaned)

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d",
        "%a, %d %b %Y %H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    # Try parsing mail-style headers with timezone names
    # (e.g. "Fri, 10 Jul 2026 12:34:56 +0000 (UTC)")

    mail_match = re.match(
        r"^[^,\n]+,\s*(\d{1,2}\s+[a-zA-Z]{3}\s+\d{4}\s+\d{2}:\d{2}:\d{2})", cleaned
    )
    if mail_match:
        try:
            return datetime.datetime.strptime(mail_match.group(1), "%d %b %Y %H:%M:%S")
        except ValueError:
            pass

    return None


def match_filters(
    content: str,
    sender: Optional[str],
    subject: Optional[str],
    timestamp: Optional[str],
    args: argparse.Namespace,
) -> bool:
    """Apply query search filters to parsed message record.

    Args:
        content: The message body/content.
        sender: The sender name.
        subject: The subject/channel name.
        timestamp: The message date/time string.
        args: Parsed command-line arguments.

    Returns:
        True if all filters match.
    """
    # pylint: disable=too-many-return-statements, too-many-branches
    # 1. Date Filter

    if timestamp and (args.after or args.before):
        dt = parse_date(timestamp)
        if dt:
            if args.after:
                limit_after = parse_date(args.after)
                if limit_after and dt < limit_after:
                    return False
            if args.before:
                limit_before = parse_date(args.before)
                if limit_before and dt > limit_before:
                    return False

    # 2. Sender Filter
    if args.sender:
        if not sender or args.sender.lower() not in sender.lower():
            return False

    # 3. Subject/Channel Filter
    if args.subject:
        if not subject or args.subject.lower() not in subject.lower():
            return False

    # 4. Text Query Filter
    if args.query:
        if args.regex:
            try:
                if not re.search(args.query, content, re.IGNORECASE):
                    return False
            except re.error:
                return False
        else:
            if args.query.lower() not in content.lower():
                return False

    return True


def search_json(
    path: Path, args: argparse.Namespace
) -> Generator[SearchResult, None, None]:
    """Search through JSON logs using heuristic keys for structures.

    Args:
        path: Path to the JSON file.
        args: Parsed command-line arguments.

    Yields:
        SearchResult entries.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.warning("Failed to parse JSON file %s: %s", path.name, err)
        return

    # Helper recursive walker to search dictionaries / list items
    def walk_json(
        node: Any, channel: Optional[str] = None
    ) -> Generator[SearchResult, None, None]:
        # pylint: disable=too-many-branches
        if isinstance(node, list):
            for item in node:
                yield from walk_json(item, channel)

        elif isinstance(node, dict):
            # Check if this dictionary represents a message object
            content_keys = ["content", "text", "message", "body", "tweet", "full_text"]
            sender_keys = [
                "sender",
                "sender_name",
                "creator",
                "author",
                "user",
                "username",
                "from",
            ]
            time_keys = [
                "timestamp",
                "created_at",
                "created_date",
                "date",
                "ts",
                "time",
            ]

            # Locate values using priority keys
            msg_content = None
            msg_sender = None
            msg_time = None
            msg_subj = channel

            for k in content_keys:
                if k in node and isinstance(node[k], str):
                    msg_content = node[k]
                    break

            for k in sender_keys:
                if k in node:
                    val = node[k]
                    if isinstance(val, dict):
                        # E.g. {"name": "Alice", "id": 123}
                        msg_sender = (
                            val.get("name")
                            or val.get("username")
                            or val.get("display_name")
                        )
                    else:
                        msg_sender = str(val)
                    break

            for k in time_keys:
                if k in node:
                    msg_time = str(node[k])
                    break

            # If we found a message body, test filters
            if msg_content is not None:
                if match_filters(msg_content, msg_sender, msg_subj, msg_time, args):
                    yield SearchResult(
                        source_file=path.as_posix(),
                        format="JSON",
                        timestamp=msg_time,
                        sender=msg_sender,
                        subject=msg_subj,
                        content=msg_content,
                    )

            # Traverse child elements to look for nested structures
            for k, val in node.items():
                # Google Chat exports have metadata in parent channel folder
                # name or specific title properties

                sub_subj = channel
                if k in [
                    "channel",
                    "room",
                    "topic",
                    "title",
                    "display_name",
                ] and isinstance(val, str):
                    sub_subj = val
                if isinstance(val, (list, dict)):
                    yield from walk_json(val, sub_subj)

    yield from walk_json(data)


def search_csv(
    path: Path, args: argparse.Namespace
) -> Generator[SearchResult, None, None]:
    """Search through CSV exports using header names or cell searches.

    Args:
        path: Path to the CSV file.
        args: Parsed command-line arguments.

    Yields:
        SearchResult entries.
    """
    # pylint: disable=too-many-locals
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            # Sniff delimiter
            sample = f.read(2048)
            f.seek(0)
            dialect = csv.Sniffer().sniff(sample) if sample else csv.excel
            reader = csv.reader(f, dialect)
            rows = list(reader)
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.warning("Failed to parse CSV file %s: %s", path.name, err)
        return

    if not rows:
        return

    header = [h.strip().lower() for h in rows[0]]
    content_idx = -1
    sender_idx = -1
    time_idx = -1
    subj_idx = -1

    # Heuristic column mappings
    for idx, col in enumerate(header):
        if col in ["text", "message", "body", "content", "comment", "tweet"]:
            content_idx = idx
        elif col in ["sender", "author", "user", "username", "from", "name"]:
            sender_idx = idx
        elif col in ["time", "date", "timestamp", "created_at"]:
            time_idx = idx
        elif col in ["subject", "channel", "room", "title", "topic"]:
            subj_idx = idx

    # Run search on row lines
    for row_num, row in enumerate(rows[1:], 2):
        if not row:
            continue
        msg_content = ""
        msg_sender = None
        msg_time = None
        msg_subj = None

        if content_idx != -1 and content_idx < len(row):
            msg_content = row[content_idx]
            msg_sender = (
                row[sender_idx] if sender_idx != -1 and sender_idx < len(row) else None
            )
            msg_time = row[time_idx] if time_idx != -1 and time_idx < len(row) else None
            msg_subj = row[subj_idx] if subj_idx != -1 and subj_idx < len(row) else None
        else:
            # Fallback: search all columns in row
            msg_content = " | ".join(row)

        if match_filters(msg_content, msg_sender, msg_subj, msg_time, args):
            yield SearchResult(
                source_file=path.as_posix(),
                format="CSV",
                timestamp=msg_time,
                sender=msg_sender,
                subject=msg_subj or f"Row {row_num}",
                content=msg_content,
            )


def get_mbox_payload(msg: mailbox.Message) -> str:
    """Safely extract plain text body payload from a mailbox message.

    Args:
        msg: mailbox.Message object.

    Returns:
        String containing message plain text content.
    """
    if msg.is_multipart():
        parts = []
        for part in msg.walk():
            content_type = part.get_content_type()
            # Prefer plain text, ignore html parts if plain text is available
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    parts.append(
                        payload.decode(
                            part.get_content_charset() or "utf-8", errors="replace"
                        )
                    )
        if parts:
            return "\n".join(parts)

        # Fallback to any text part
        for part in msg.walk():
            if part.get_content_maintype() == "text":
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    return payload.decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
        return ""

    payload = msg.get_payload(decode=True)
    if isinstance(payload, bytes):
        return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")

    return ""


def search_mbox(
    path: Path, args: argparse.Namespace
) -> Generator[SearchResult, None, None]:
    """Search through MBOX files using mailbox library.

    Args:
        path: Path to the MBOX file.
        args: Parsed command-line arguments.

    Yields:
        SearchResult entries.
    """
    try:
        mbox = mailbox.mbox(path)
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.warning("Failed to open MBOX archive %s: %s", path.name, err)
        return

    for key in mbox.keys():
        try:
            msg = mbox.get(key)
            if msg is None:
                continue
            msg_sender = msg.get("From")
            msg_time = msg.get("Date")
            msg_subj = msg.get("Subject")
            msg_content = get_mbox_payload(msg)

            if match_filters(msg_content, msg_sender, msg_subj, msg_time, args):
                yield SearchResult(
                    source_file=path.as_posix(),
                    format="MBOX",
                    timestamp=msg_time,
                    sender=msg_sender,
                    subject=msg_subj,
                    content=msg_content,
                )
        except Exception as err:  # pylint: disable=broad-exception-caught
            logger.debug("Failed to read MBOX message %s: %s", key, err)
            continue


def search_html(
    path: Path, args: argparse.Namespace
) -> Generator[SearchResult, None, None]:
    """Search through HTML export documents.

    Args:
        path: Path to the HTML file.
        args: Parsed command-line arguments.

    Yields:
        SearchResult entries.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.warning("Failed to read HTML file %s: %s", path.name, err)
        return

    # Parse and extract text parts
    extractor = SimpleHTMLTextExtractor()
    try:
        extractor.feed(content)
        plain_text = extractor.get_text()
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.debug("Failed to extract HTML text: %s", err)
        plain_text = re.sub(r"<[^>]*>", "", content)  # basic fallback regex
        extractor.title = path.name

    # Check matches on the entire body or paragraph lines
    lines = [line.strip() for line in plain_text.split("\n") if line.strip()]
    for line in lines:
        if match_filters(line, None, extractor.title, None, args):

            yield SearchResult(
                source_file=path.as_posix(),
                format="HTML",
                timestamp=None,
                sender=None,
                subject=extractor.title or path.name,
                content=line,
            )


def format_text_result(res: SearchResult) -> str:
    """Pretty-format a search result for terminal layout."""
    ts = res.timestamp or "N/A"
    sender = res.sender or "N/A"
    subj = res.subject or "N/A"
    # Truncate content to keep formatting readable
    content_lines = res.content.split("\n")
    snippet = content_lines[0]
    if len(content_lines) > 1 or len(snippet) > 120:
        snippet = snippet[:120] + "..."

    return (
        f"[{res.format}] File: {Path(res.source_file).name}\n"
        f"  Date: {ts} | Sender: {sender} | Context: {subj}\n"
        f"  Match: {snippet}\n"
    )


def execute_search(args: argparse.Namespace) -> List[SearchResult]:
    """Run search pipelines depending on file paths and formats.

    Args:
        args: Command-line arguments.

    Returns:
        List of SearchResult items.
    """
    results = []
    target = Path(args.input)

    if target.is_file():
        files = [target]
    elif target.is_dir():
        # Find all files with supported extensions recursively
        extensions = [".json", ".csv", ".mbox", ".html", ".htm"]
        files = [
            p
            for p in target.rglob("*")
            if p.suffix.lower() in extensions and p.is_file()
        ]
    else:
        logger.error("Input path is neither a file nor directory: %s", target)
        return []

    logger.info("Found %d files to scan.", len(files))

    for p in files:
        suffix = p.suffix.lower()
        logger.debug("Scanning file: %s", p.as_posix())
        generator = None
        if suffix == ".json":
            generator = search_json(p, args)
        elif suffix == ".csv":
            generator = search_csv(p, args)
        elif suffix == ".mbox":
            generator = search_mbox(p, args)
        elif suffix in [".html", ".htm"]:
            generator = search_html(p, args)

        if generator:
            for item in generator:
                results.append(item)

    return results


def main() -> None:
    """CLI execution entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Personal Data Export Searcher — search archives from "
            "chat apps, email, or social media locally."
        )
    )

    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Input archive file or directory containing exports.",
    )
    parser.add_argument("-q", "--query", help="Keyword or regex string to match.")
    parser.add_argument(
        "--regex",
        action="store_true",
        help="Treat query string as a regular expression.",
    )
    parser.add_argument("--sender", help="Filter matches by sender name or ID.")
    parser.add_argument(
        "--subject", help="Filter matches by subject/channel/context name."
    )
    parser.add_argument(
        "--after", help="Filter matches created after this date (YYYY-MM-DD)."
    )
    parser.add_argument(
        "--before", help="Filter matches created before this date (YYYY-MM-DD)."
    )
    parser.add_argument(
        "-o", "--output", help="Save search results to this output path."
    )
    parser.add_argument(
        "--format",
        choices=["text", "json", "csv"],
        default="text",
        help="Output format to print/save search results (default: text).",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose debug logging."
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    results = execute_search(args)
    logger.info("Search finished. Found %d matches.", len(results))

    # Serialize results
    if args.output:
        out_path = Path(args.output)
        try:
            if args.format == "json":
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump([asdict(r) for r in results], f, indent=2)
            elif args.format == "csv":
                with open(out_path, "w", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        [
                            "source_file",
                            "format",
                            "timestamp",
                            "sender",
                            "subject",
                            "content",
                        ]
                    )
                    for r in results:
                        writer.writerow(
                            [
                                r.source_file,
                                r.format,
                                r.timestamp,
                                r.sender,
                                r.subject,
                                r.content,
                            ]
                        )
            else:
                with open(out_path, "w", encoding="utf-8") as f:
                    for r in results:
                        f.write(format_text_result(r))
            logger.info("Saved search results to: %s", out_path.as_posix())
        except Exception as err:  # pylint: disable=broad-exception-caught
            logger.error("Failed to write search output: %s", err)
            sys.exit(1)

    else:
        # Output to terminal
        for r in results:
            sys.stdout.write(format_text_result(r))


if __name__ == "__main__":
    main()
