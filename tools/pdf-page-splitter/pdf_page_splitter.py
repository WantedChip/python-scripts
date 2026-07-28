"""Splits a PDF into individual pages, page ranges, or page chunks.

This tool extracts pages from a PDF file using pypdf into separate PDF documents
or multi-page chunk files with password decryption support.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional, Set

from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)


def parse_page_ranges(ranges_str: str, max_pages: int) -> Set[int]:
    """Parse comma-separated page ranges (e.g. "1-3,5,8-10") into 0-indexed page set.

    Args:
        ranges_str: Range string specification.
        max_pages: Total number of pages in the source PDF.

    Returns:
        Set of 0-indexed integer page numbers to extract.
    """
    selected: Set[int] = set()
    parts = ranges_str.split(",")

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


def split_pdf_file(
    input_path: Path,
    output_dir: Path,
    ranges_str: Optional[str] = None,
    chunk_size: Optional[int] = None,
    password: Optional[str] = None,
) -> List[Path]:
    """Split a source PDF into individual page files, specified ranges, or chunks.

    Args:
        input_path: Path to source PDF file.
        output_dir: Destination directory for generated split PDFs.
        ranges_str: Optional page range specification string (e.g. "1-3,5").
        chunk_size: Optional chunk size for grouping N pages per file.
        password: Optional password for encrypted source PDF.

    Returns:
        List of generated split PDF file paths.
    """
    reader = PdfReader(str(input_path))
    if reader.is_encrypted:
        if password:
            reader.decrypt(password)
        else:
            logger.error("PDF is encrypted but no password was provided.")
            return []

    total_pages = len(reader.pages)
    if total_pages == 0:
        logger.error("Source PDF contains zero pages.")
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    generated_files: List[Path] = []
    stem = input_path.stem

    if ranges_str:
        selected_pages = parse_page_ranges(ranges_str, total_pages)
        if not selected_pages:
            logger.error("No valid pages selected by range spec: %s", ranges_str)
            return []

        out_name = f"{stem}_pages_{ranges_str.replace(',', '_')}.pdf"
        out_file = output_dir / out_name
        writer = PdfWriter()
        for p_idx in sorted(selected_pages):
            writer.add_page(reader.pages[p_idx])

        with open(out_file, "wb") as f_out:
            writer.write(f_out)
        writer.close()
        generated_files.append(out_file)

    elif chunk_size and chunk_size > 0:
        for i in range(0, total_pages, chunk_size):
            end_i = min(i + chunk_size, total_pages)
            chunk_num = (i // chunk_size) + 1
            out_name = f"{stem}_chunk_{chunk_num:03d}_p{i+1}-p{end_i}.pdf"
            out_file = output_dir / out_name

            writer = PdfWriter()
            for p_idx in range(i, end_i):
                writer.add_page(reader.pages[p_idx])

            with open(out_file, "wb") as f_out:
                writer.write(f_out)
            writer.close()
            generated_files.append(out_file)

    else:
        # Default mode: split each page into a separate file
        for p_idx, page in enumerate(reader.pages):
            out_name = f"{stem}_page_{p_idx + 1:03d}.pdf"
            out_file = output_dir / out_name

            writer = PdfWriter()
            writer.add_page(page)
            with open(out_file, "wb") as f_out:
                writer.write(f_out)
            writer.close()
            generated_files.append(out_file)

    return generated_files


def main(args: Optional[List[str]] = None) -> int:
    """Run CLI entry point for PDF page splitter tool.

    Args:
        args: Command line argument list.

    Returns:
        Exit code integer (0 for success, non-zero for failure).
    """
    parser = argparse.ArgumentParser(
        description="Split PDF into individual pages, ranges, or page chunks."
    )
    parser.add_argument("input_pdf", type=str, help="Path to input PDF file.")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=str,
        default=None,
        help="Target output directory for split PDFs.",
    )
    parser.add_argument(
        "-r",
        "--ranges",
        type=str,
        default=None,
        help="Page ranges to extract (e.g. '1-3,5,8-10').",
    )
    parser.add_argument(
        "-c",
        "--chunk-size",
        type=int,
        default=None,
        help="Split into files of N pages each (e.g. 5).",
    )
    parser.add_argument(
        "-p",
        "--password",
        type=str,
        default=None,
        help="Password for encrypted input PDF.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging."
    )

    parsed_args = parser.parse_args(args)

    level = logging.DEBUG if parsed_args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    input_path = Path(parsed_args.input_pdf)
    if not input_path.exists() or not input_path.is_file():
        logger.error("Input PDF file does not exist: %s", input_path)
        return 1

    out_dir = (
        Path(parsed_args.output_dir)
        if parsed_args.output_dir
        else input_path.parent / f"{input_path.stem}_split"
    )

    logger.info("Splitting PDF %s...", input_path.resolve())
    generated = split_pdf_file(
        input_path,
        out_dir,
        parsed_args.ranges,
        parsed_args.chunk_size,
        parsed_args.password,
    )

    if generated:
        logger.info(
            "Successfully created %d split files in %s",
            len(generated),
            out_dir.resolve(),
        )
        return 0

    logger.error("Failed to split PDF file.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
