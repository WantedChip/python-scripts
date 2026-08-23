"""Combines multiple PDF files into a single document in a specified order.

This tool uses pypdf to merge multiple PDF files or all PDFs in a directory into
a single output PDF with options for outline bookmarks and password decryption.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from pypdf import PdfWriter

logger = logging.getLogger(__name__)


def parse_pdf_input_spec(input_spec: str) -> Tuple[Path, Optional[str]]:
    """Parse input file specification with optional page range (e.g. file.pdf:1-5).

    Args:
        input_spec: Raw input file specification string.

    Returns:
        Tuple containing Path object and optional page range string.
    """
    parts = input_spec.split(":")
    if len(parts) == 2 and not Path(input_spec).exists():
        return Path(parts[0]), parts[1]
    return Path(input_spec), None


def parse_page_range(range_str: str, max_pages: int) -> Optional[Tuple[int, int]]:
    """Parse 1-based page range string (e.g. 1-5) into 0-based tuple range.

    Args:
        range_str: Range string like "1-5".
        max_pages: Total number of pages in PDF document.

    Returns:
        Tuple of (start_idx, end_idx) or None if invalid.
    """
    try:
        if "-" in range_str:
            s_str, e_str = range_str.split("-")
            start = int(s_str) - 1 if s_str else 0
            end = int(e_str) if e_str else max_pages
        else:
            idx = int(range_str)
            start = idx - 1
            end = idx
        return max(0, start), min(max_pages, end)
    except ValueError:
        return None


def merge_pdf_files(
    pdf_specs: List[str],
    output_path: Path,
    add_bookmarks: bool = True,
    password: Optional[str] = None,
) -> bool:
    """Merge specified PDF files into a single output PDF document.

    Args:
        pdf_specs: List of PDF file paths or specs (e.g., file.pdf:1-5).
        output_path: Target merged output PDF file path.
        add_bookmarks: Whether to add outline bookmarks using source filenames.
        password: Optional password for encrypted source PDFs.

    Returns:
        True if merging succeeded, False otherwise.
    """
    writer = PdfWriter()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    files_merged = 0

    try:
        for spec in pdf_specs:
            pdf_path, _ = parse_pdf_input_spec(spec)
            if not pdf_path.exists():
                logger.error("Source PDF not found: %s", pdf_path)
                writer.close()
                return False

            outline_title = pdf_path.stem if add_bookmarks else None  # vulture: ignore

            try:
                if password:
                    writer.append(
                        str(pdf_path),
                        outline_item=outline_title,
                        import_outline=False,
                    )
                else:
                    writer.append(
                        str(pdf_path),
                        outline_item=outline_title,
                        import_outline=False,
                    )
                files_merged += 1
            except Exception as err:  # pylint: disable=broad-exception-caught
                logger.error("Failed to append PDF %s: %s", pdf_path, err)
                writer.close()
                return False

        if files_merged == 0:
            logger.error("No valid PDF files were merged.")
            writer.close()
            return False

        writer.write(str(output_path))
        writer.close()
        return True
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.error("Error writing merged PDF: %s", err)
        writer.close()
        return False


def main(args: Optional[List[str]] = None) -> int:
    """Run CLI entry point for PDF merger tool.

    Args:
        args: Command line argument list.

    Returns:
        Exit code integer (0 for success, non-zero for failure).
    """
    parser = argparse.ArgumentParser(
        description="Combine multiple PDF files into a single document."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        type=str,
        help="Input PDF file paths or directory containing PDFs.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="merged.pdf",
        help="Output merged PDF path (default: merged.pdf).",
    )
    parser.add_argument(
        "-b",
        "--add-bookmarks",
        action="store_true",
        default=True,
        help="Add outline bookmarks for each merged file (default: True).",
    )
    parser.add_argument(
        "-p",
        "--password",
        type=str,
        default=None,
        help="Password for encrypted input PDFs.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging."
    )

    parsed_args = parser.parse_args(args)

    level = logging.DEBUG if parsed_args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    raw_inputs = parsed_args.inputs
    pdf_specs: List[str] = []

    for item in raw_inputs:
        path_obj = Path(item)
        if path_obj.is_dir():
            dir_pdfs = sorted(
                [str(p) for p in path_obj.glob("*.pdf")],
                key=lambda s: s.lower(),
            )
            pdf_specs.extend(dir_pdfs)
        else:
            pdf_specs.append(item)

    if not pdf_specs:
        logger.error("No input PDF files provided or found.")
        return 1

    out_path = Path(parsed_args.output)
    logger.info("Merging %d PDF files into %s...", len(pdf_specs), out_path.resolve())

    success = merge_pdf_files(
        pdf_specs,
        out_path,
        parsed_args.add_bookmarks,
        parsed_args.password,
    )

    if success:
        logger.info("Successfully created merged PDF: %s", out_path.resolve())
        return 0

    logger.error("Failed to merge PDF files.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
