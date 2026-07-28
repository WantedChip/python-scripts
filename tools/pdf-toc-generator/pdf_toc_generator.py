"""Generates a table of contents PDF from heading-detected page analysis or config.

This module embeds interactive outline bookmarks into PDF documents using pypdf,
supporting automated heading detection or JSON outline definitions.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-nested-blocks,broad-exception-caught

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)

DEFAULT_HEADING_PATTERN = r"^(?:chapter|section|\d+\.|\b[A-Z0-9\s]{4,30}\b)"


def detect_headings_in_pdf(
    input_pdf: Path,
    heading_pattern: str = DEFAULT_HEADING_PATTERN,
    password: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Scan PDF text per page to auto-detect heading titles.

    Args:
        input_pdf: Source PDF file path.
        heading_pattern: Regex pattern for heading detection.
        password: Optional password for encrypted source PDF.

    Returns:
        List of outline dictionaries with title and 1-based page number.
    """
    entries: List[Dict[str, Any]] = []
    try:
        compiled_re = re.compile(heading_pattern, re.IGNORECASE)
        reader = PdfReader(str(input_pdf))
        if reader.is_encrypted:
            if password:
                reader.decrypt(password)
            else:
                return entries

        for page_idx, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            for line in text.splitlines():
                clean_line = line.strip()
                if clean_line and compiled_re.search(clean_line):
                    entries.append(
                        {
                            "title": clean_line[:60],
                            "page": page_idx,
                            "level": 0,
                        }
                    )
                    break  # Take first matching heading per page
    except Exception as err:
        logger.error("Error auto-detecting headings in %s: %s", input_pdf, err)
    return entries


def add_toc_bookmarks(
    input_pdf: Path,
    output_pdf: Path,
    toc_entries: List[Dict[str, Any]],
    password: Optional[str] = None,
) -> bool:
    """Add interactive outline bookmarks to PDF document.

    Args:
        input_pdf: Source PDF document path.
        output_pdf: Destination PDF document path.
        toc_entries: List of dicts specifying title, page, and level.
        password: Optional password for encrypted source PDF.

    Returns:
        True if bookmarks were successfully written, False otherwise.
    """
    try:
        reader = PdfReader(str(input_pdf))
        if reader.is_encrypted:
            if password:
                reader.decrypt(password)
            else:
                logger.error("Source PDF %s is encrypted.", input_pdf.name)
                return False

        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        total_pages = len(reader.pages)

        for entry in toc_entries:
            title = str(entry.get("title", "Untitled"))
            page_num = int(entry.get("page", 1))
            if 1 <= page_num <= total_pages:
                writer.add_outline_item(title, page_num - 1)

        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        with open(output_pdf, "wb") as f_out:
            writer.write(f_out)

        writer.close()
        return True
    except Exception as err:
        logger.error("Failed to add TOC bookmarks to %s: %s", input_pdf.name, err)
        return False


def main(args: Optional[List[str]] = None) -> int:
    """Run CLI entry point for PDF TOC generator tool.

    Args:
        args: Command line argument list.

    Returns:
        Exit code integer (0 for success, non-zero for failure).
    """
    parser = argparse.ArgumentParser(
        description=(
            "Generates a table of contents PDF from page analysis or JSON" " outline."
        )
    )
    parser.add_argument("input_pdf", type=str, help="Source PDF file path.")
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Destination modified PDF output path.",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default=None,
        help="JSON file defining outline entries [{'title': '...', 'page': 1}].",
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default=DEFAULT_HEADING_PATTERN,
        help="Regex pattern for automatic heading detection.",
    )
    parser.add_argument(
        "-p",
        "--password",
        type=str,
        default=None,
        help="Password for encrypted PDF.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging."
    )

    parsed_args = parser.parse_args(args)

    level = logging.DEBUG if parsed_args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    input_path = Path(parsed_args.input_pdf)
    if not input_path.exists() or not input_path.is_file():
        logger.error("Source PDF file does not exist: %s", input_path)
        return 1

    entries: List[Dict[str, Any]] = []

    if parsed_args.config:
        config_path = Path(parsed_args.config)
        if not config_path.exists() or not config_path.is_file():
            logger.error("Config JSON file does not exist: %s", config_path)
            return 1
        try:
            with open(config_path, "r", encoding="utf-8") as f_json:
                entries = json.load(f_json)
        except Exception as err:
            logger.error("Failed to parse JSON config file: %s", err)
            return 1
    else:
        logger.info("Auto-detecting headings in %s...", input_path.name)
        entries = detect_headings_in_pdf(
            input_path, parsed_args.pattern, parsed_args.password
        )

    if not entries:
        logger.warning(
            "No table of contents entries found or configured for %s",
            input_path.name,
        )

    out_path = (
        Path(parsed_args.output)
        if parsed_args.output
        else input_path.parent / f"{input_path.stem}_toc.pdf"
    )

    logger.info("Writing TOC bookmarks into %s...", out_path.name)
    if add_toc_bookmarks(input_path, out_path, entries, parsed_args.password):
        logger.info("Successfully exported PDF with TOC to %s", out_path)
        return 0

    logger.error("Failed to export PDF with TOC.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
