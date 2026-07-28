"""Searches for keywords across multiple PDF and text files in a folder.

This module inspects PDF, TXT, CSV, JSON, and Markdown documents for match terms,
reporting line/page numbers and snippet contexts.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-nested-blocks,broad-exception-caught

import argparse
import csv
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Pattern

from pypdf import PdfReader

logger = logging.getLogger(__name__)


def search_text_file(file_path: Path, pattern: Pattern[str]) -> List[Dict[str, Any]]:
    """Search plain text or markdown file for matching lines.

    Args:
        file_path: Path to text file.
        pattern: Compiled regex search pattern.

    Returns:
        List of match occurrence dictionaries.
    """
    matches: List[Dict[str, Any]] = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f_in:
            for line_idx, line in enumerate(f_in, 1):
                if pattern.search(line):
                    matches.append(
                        {
                            "file": str(file_path),
                            "filename": file_path.name,
                            "location": f"Line {line_idx}",
                            "line_num": line_idx,
                            "page_num": None,
                            "snippet": line.strip()[:120],
                        }
                    )
    except Exception as err:
        logger.debug("Failed to search text file %s: %s", file_path, err)
    return matches


def search_pdf_file(
    file_path: Path, pattern: Pattern[str], password: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Search PDF document for matching text per page.

    Args:
        file_path: Path to target PDF file.
        pattern: Compiled regex search pattern.
        password: Optional password for encrypted source PDF.

    Returns:
        List of match occurrence dictionaries.
    """
    matches: List[Dict[str, Any]] = []
    try:
        reader = PdfReader(str(file_path))
        if reader.is_encrypted:
            if password:
                reader.decrypt(password)
            else:
                return matches

        for page_idx, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            lines = text.splitlines()
            for line in lines:
                if pattern.search(line):
                    matches.append(
                        {
                            "file": str(file_path),
                            "filename": file_path.name,
                            "location": f"Page {page_idx}",
                            "line_num": None,
                            "page_num": page_idx,
                            "snippet": line.strip()[:120],
                        }
                    )
    except Exception as err:
        logger.debug("Failed to search PDF file %s: %s", file_path, err)
    return matches


def search_directory(
    target_dir: Path,
    query: str,
    is_regex: bool = False,
    ignore_case: bool = True,
    recursive: bool = False,
    password: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search all supported files in directory for matching query.

    Args:
        target_dir: Target directory path.
        query: Query string or regex pattern.
        is_regex: Whether to treat query as regex pattern.
        ignore_case: Case-insensitive match flag.
        recursive: Search subdirectories flag.
        password: Optional password for encrypted PDFs.

    Returns:
        List of match occurrence dictionaries.
    """
    flags = re.IGNORECASE if ignore_case else 0
    pattern_str = query if is_regex else re.escape(query)
    compiled_pattern = re.compile(pattern_str, flags)

    all_matches: List[Dict[str, Any]] = []
    glob_pattern = "**/*" if recursive else "*"

    for p in sorted(list(target_dir.glob(glob_pattern)), key=lambda x: x.name):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext == ".pdf":
            all_matches.extend(search_pdf_file(p, compiled_pattern, password))
        elif ext in (
            ".txt",
            ".md",
            ".csv",
            ".json",
            ".py",
            ".log",
            ".rst",
            ".yaml",
            ".yml",
        ):
            all_matches.extend(search_text_file(p, compiled_pattern))

    return all_matches


def main(args: Optional[List[str]] = None) -> int:
    """Run CLI entry point for document text search tool.

    Args:
        args: Command line argument list.

    Returns:
        Exit code integer (0 for success, non-zero for failure).
    """
    parser = argparse.ArgumentParser(
        description="Search for keywords across PDF and text files in a folder."
    )
    parser.add_argument("directory", type=str, help="Source directory path.")
    parser.add_argument("query", type=str, help="Search keyword or regex pattern.")
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Search subdirectories recursively.",
    )
    parser.add_argument(
        "--regex", action="store_true", help="Treat query as regular expression."
    )
    parser.add_argument(
        "-i",
        "--ignore-case",
        action="store_true",
        default=True,
        help="Perform case-insensitive search (default: True).",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format (default: table).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Destination summary report path.",
    )
    parser.add_argument(
        "-p",
        "--password",
        type=str,
        default=None,
        help="Password for encrypted PDFs.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging."
    )

    parsed_args = parser.parse_args(args)

    level = logging.DEBUG if parsed_args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    target_dir = Path(parsed_args.directory)
    if not target_dir.exists() or not target_dir.is_dir():
        logger.error("Target directory does not exist: %s", target_dir)
        return 1

    matches = search_directory(
        target_dir,
        parsed_args.query,
        parsed_args.regex,
        parsed_args.ignore_case,
        parsed_args.recursive,
        parsed_args.password,
    )

    if parsed_args.output:
        out_path = Path(parsed_args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.suffix.lower() == ".json":
            with open(out_path, "w", encoding="utf-8") as f_out:
                json.dump(matches, f_out, indent=2)
        else:
            fieldnames = ["filename", "location", "snippet", "file"]
            with open(out_path, "w", newline="", encoding="utf-8") as f_csv:
                writer = csv.DictWriter(
                    f_csv, fieldnames=fieldnames, extrasaction="ignore"
                )
                writer.writeheader()
                writer.writerows(matches)
        logger.info("Search report exported to %s", out_path)

    if parsed_args.format == "json":
        print(json.dumps(matches, indent=2))
    elif parsed_args.format == "csv":
        writer = csv.DictWriter(
            sys.stdout,
            fieldnames=["filename", "location", "snippet"],
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(matches)
    else:  # table
        print(
            f"\nDocument Search Results for '{parsed_args.query}' "
            f"({len(matches)} matches)"
        )
        print("-" * 75)
        print(f"{'Filename':<28} | {'Location':<12} | {'Snippet':<30}")
        print("-" * 75)
        for m in matches:
            fname = (
                m["filename"][:25] + "..." if len(m["filename"]) > 28 else m["filename"]
            )
            snippet = (
                m["snippet"][:27] + "..." if len(m["snippet"]) > 30 else m["snippet"]
            )
            print(f"{fname:<28} | {m['location']:<12} | {snippet:<30}")
        print("-" * 75 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
