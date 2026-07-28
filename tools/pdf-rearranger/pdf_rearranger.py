"""Reorders, rotates, or deletes specific pages from a PDF file.

This module manipulates PDF page orders, applies rotation angles (90, 180, 270),
and excludes deleted page selections using pypdf.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments
# pylint: disable=broad-exception-caught

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional, Set

from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)


def parse_page_indices(selection_str: str, max_pages: int) -> List[int]:
    """Parse page selection string (e.g. '3,1-2,5') into 0-indexed page list.

    Args:
        selection_str: Selection string specification.
        max_pages: Maximum number of pages in document.

    Returns:
        List of 0-indexed integer page numbers.
    """
    indices: List[int] = []
    parts = selection_str.split(",")
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
                        indices.append(page_num - 1)
            except ValueError:
                logger.warning("Invalid page range slice: %s", clean)
        else:
            try:
                page_num = int(clean)
                if 1 <= page_num <= max_pages:
                    indices.append(page_num - 1)
            except ValueError:
                logger.warning("Invalid page number: %s", clean)
    return indices


def rearrange_pdf_pages(
    input_pdf: Path,
    output_pdf: Path,
    reorder_str: Optional[str] = None,
    rotate_angle: Optional[int] = None,
    rotate_pages_str: Optional[str] = None,
    delete_str: Optional[str] = None,
    password: Optional[str] = None,
) -> bool:
    """Reorder, rotate, or delete pages from source PDF document.

    Args:
        input_pdf: Source PDF file path.
        output_pdf: Destination PDF file path.
        reorder_str: Optional custom page order sequence string.
        rotate_angle: Optional rotation angle (90, 180, 270 degrees).
        rotate_pages_str: Optional string specifying pages to rotate.
        delete_str: Optional string specifying pages to delete.
        password: Optional password for encrypted source PDF.

    Returns:
        True if PDF page manipulation succeeded, False otherwise.
    """
    try:
        reader = PdfReader(str(input_pdf))
        if reader.is_encrypted:
            if password:
                reader.decrypt(password)
            else:
                logger.error("Source PDF %s is encrypted.", input_pdf.name)
                return False

        total_pages = len(reader.pages)

        # Determine target page sequence
        if reorder_str:
            target_indices = parse_page_indices(reorder_str, total_pages)
        else:
            target_indices = list(range(total_pages))

        # Filter out deleted pages
        if delete_str:
            delete_set: Set[int] = set(parse_page_indices(delete_str, total_pages))
            target_indices = [idx for idx in target_indices if idx not in delete_set]

        if not target_indices:
            logger.error("No valid pages remain after filtering/reordering.")
            return False

        # Determine pages to rotate
        rotate_set: Set[int] = set()
        if rotate_angle and rotate_angle % 90 == 0:
            if rotate_pages_str:
                rotate_set = set(parse_page_indices(rotate_pages_str, total_pages))
            else:
                rotate_set = set(range(total_pages))

        writer = PdfWriter()

        for idx in target_indices:
            page = reader.pages[idx]
            if rotate_angle and idx in rotate_set:
                page.rotate(rotate_angle)
            writer.add_page(page)

        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        with open(output_pdf, "wb") as f_out:
            writer.write(f_out)

        writer.close()
        return True
    except Exception as err:
        logger.error("Failed to rearrange PDF %s: %s", input_pdf.name, err)
        return False


def main(args: Optional[List[str]] = None) -> int:
    """Run CLI entry point for PDF rearranger tool.

    Args:
        args: Command line argument list.

    Returns:
        Exit code integer (0 for success, non-zero for failure).
    """
    parser = argparse.ArgumentParser(
        description="Reorder, rotate, or delete specific pages from a PDF file."
    )
    parser.add_argument("input_pdf", type=str, help="Source PDF file path.")
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Destination modified output PDF path.",
    )
    parser.add_argument(
        "-r",
        "--reorder",
        type=str,
        default=None,
        help="Custom page order (e.g. '3,1,2,4-5').",
    )
    parser.add_argument(
        "--rotate",
        type=int,
        choices=[90, 180, 270],
        default=None,
        help="Angle to rotate pages clockwise (90, 180, 270).",
    )
    parser.add_argument(
        "--rotate-pages",
        type=str,
        default=None,
        help="Target pages to rotate (e.g. '1,3'). All if omitted.",
    )
    parser.add_argument(
        "-d",
        "--delete",
        type=str,
        default=None,
        help="Pages to delete/exclude (e.g. '2,4').",
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

    out_path = (
        Path(parsed_args.output)
        if parsed_args.output
        else input_path.parent / f"{input_path.stem}_rearranged.pdf"
    )

    logger.info("Rearranging pages for %s -> %s...", input_path.name, out_path.name)
    success = rearrange_pdf_pages(
        input_path,
        out_path,
        parsed_args.reorder,
        parsed_args.rotate,
        parsed_args.rotate_pages,
        parsed_args.delete,
        parsed_args.password,
    )

    if success:
        logger.info("Successfully exported rearranged PDF to %s", out_path)
        return 0

    logger.error("Failed to export rearranged PDF.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
