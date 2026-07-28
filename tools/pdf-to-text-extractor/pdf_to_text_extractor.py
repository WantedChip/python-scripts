"""Extracts plain text from PDF files for indexing or further processing.

This module reads PDF documents using pypdf and extracts clean text into
standalone text files, JSON datasets, or console stdout with page range options.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from pypdf import PdfReader

logger = logging.getLogger(__name__)


def parse_page_range(range_str: str, max_pages: int) -> Set[int]:
    """Parse page range string (e.g. "1-5,7") into 0-indexed page set.

    Args:
        range_str: Range string specification.
        max_pages: Maximum page count of PDF document.

    Returns:
        Set of 0-indexed integer page numbers.
    """
    selected: Set[int] = set()
    parts = range_str.split(",")
    for p in parts:
        clean = p.strip()
        if not clean:
            continue
        if "-" in clean:
            bounds = clean.split("-")
            try:
                start = int(bounds[0]) if bounds[0] else 1
                end = int(bounds[1]) if bounds[1] else max_pages
                for page_num in range(start, end + 1):
                    if 1 <= page_num <= max_pages:
                        selected.add(page_num - 1)
            except ValueError:
                logger.warning("Invalid range sequence: %s", clean)
        else:
            try:
                page_num = int(clean)
                if 1 <= page_num <= max_pages:
                    selected.add(page_num - 1)
            except ValueError:
                logger.warning("Invalid page number: %s", clean)
    return selected


def extract_text_from_pdf(
    pdf_path: Path,
    range_str: Optional[str] = None,
    password: Optional[str] = None,
) -> Dict[str, Any]:
    """Extract plain text from a single PDF document.

    Args:
        pdf_path: Path to source PDF file.
        range_str: Optional page range specification string.
        password: Optional password for encrypted source PDF.

    Returns:
        Dictionary containing page texts, total pages, and full extracted text.
    """
    try:
        reader = PdfReader(str(pdf_path))
        if reader.is_encrypted:
            if password:
                reader.decrypt(password)
            else:
                return {
                    "file": str(pdf_path),
                    "filename": pdf_path.name,
                    "total_pages": 0,
                    "pages": {},
                    "full_text": "",
                    "status": "encrypted_password_required",
                }

        total_pages = len(reader.pages)
        if range_str:
            target_indices = sorted(parse_page_range(range_str, total_pages))
        else:
            target_indices = list(range(total_pages))

        pages_dict: Dict[int, str] = {}
        text_chunks: List[str] = []

        for p_idx in target_indices:
            try:
                page_text = reader.pages[p_idx].extract_text() or ""
                pages_dict[p_idx + 1] = page_text
                if page_text.strip():
                    text_chunks.append(f"--- Page {p_idx + 1} ---\n{page_text.strip()}")
            except Exception as err:  # pylint: disable=broad-exception-caught
                logger.warning(
                    "Error extracting page %d of %s: %s", p_idx + 1, pdf_path, err
                )

        full_text = "\n\n".join(text_chunks)
        return {
            "file": str(pdf_path),
            "filename": pdf_path.name,
            "total_pages": total_pages,
            "extracted_pages": len(pages_dict),
            "pages": pages_dict,
            "full_text": full_text,
            "status": "ok",
        }
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.error("Failed to read PDF file %s: %s", pdf_path, err)
        return {
            "file": str(pdf_path),
            "filename": pdf_path.name,
            "total_pages": 0,
            "pages": {},
            "full_text": "",
            "status": f"error: {err}",
        }


def main(args: Optional[List[str]] = None) -> int:
    """Run CLI entry point for PDF to text extractor tool.

    Args:
        args: Command line argument list.

    Returns:
        Exit code integer (0 for success, non-zero for failure).
    """
    parser = argparse.ArgumentParser(
        description="Extract plain text from PDF files for indexing or analysis."
    )
    parser.add_argument(
        "input_path", type=str, help="Source PDF file path or directory."
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Destination output text file path or directory.",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["txt", "json"],
        default="txt",
        help="Output text format (default: txt).",
    )
    parser.add_argument(
        "-r",
        "--pages",
        type=str,
        default=None,
        help="Page range filter (e.g. '1-5,7').",
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

    input_path = Path(parsed_args.input_path)
    if not input_path.exists():
        logger.error("Specified input path does not exist: %s", input_path)
        return 1

    pdf_files: List[Path] = []
    if input_path.is_file():
        pdf_files.append(input_path)
    elif input_path.is_dir():
        pdf_files = sorted(list(input_path.glob("*.pdf")), key=lambda p: p.name.lower())

    if not pdf_files:
        logger.error("No PDF files found at specified path.")
        return 1

    results: List[Dict[str, Any]] = []
    for pdf_file in pdf_files:
        logger.info("Extracting text from %s...", pdf_file.name)
        res = extract_text_from_pdf(pdf_file, parsed_args.pages, parsed_args.password)
        results.append(res)

    if parsed_args.output:
        out_path = Path(parsed_args.output)
        if len(results) == 1 and not out_path.is_dir():
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if parsed_args.format == "json":
                with open(out_path, "w", encoding="utf-8") as f_out:
                    json.dump(results[0], f_out, indent=2)
            else:
                with open(out_path, "w", encoding="utf-8") as f_out:
                    f_out.write(results[0]["full_text"])
            logger.info("Extracted text exported to %s", out_path)
        else:
            out_path.mkdir(parents=True, exist_ok=True)
            for item in results:
                ext = ".json" if parsed_args.format == "json" else ".txt"
                file_out = out_path / f"{Path(item['filename']).stem}_text{ext}"
                if parsed_args.format == "json":
                    with open(file_out, "w", encoding="utf-8") as f_out:
                        json.dump(item, f_out, indent=2)
                else:
                    with open(file_out, "w", encoding="utf-8") as f_out:
                        f_out.write(item["full_text"])
            logger.info("Extracted text files saved to %s", out_path)
    else:
        for item in results:
            if parsed_args.format == "json":
                print(json.dumps(item, indent=2))
            else:
                print(f"=== {item['filename']} ===")
                print(item["full_text"])
                print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
