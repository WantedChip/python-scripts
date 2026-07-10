"""PDF Batch Toolkit.

Provides CLI tools for merging, splitting, rotating, extracting, compressing,
and renaming PDF files.
"""

import argparse
import datetime
import logging
import sys
from pathlib import Path
from typing import List, Set

from pypdf import PdfReader, PdfWriter

# Setup logger
logger = logging.getLogger("pdf_toolkit")


def setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity flag.

    Args:
        verbose: If True, log level is set to DEBUG. Otherwise INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.setLevel(level)
    logger.addHandler(handler)
    # Configure root logger minimal settings so external libraries don't pollute
    logging.basicConfig(level=logging.WARNING, handlers=[handler])


def parse_page_range(range_str: str, max_pages: int) -> Set[int]:
    """Parse page range string (e.g. '1-3,5,8-10') into 0-based indices.

    Args:
        range_str: Comma-separated list of page numbers and ranges (1-based).
        max_pages: The total number of pages in the PDF.

    Returns:
        A set of 0-based page indices.

    Raises:
        ValueError: If the page range format is invalid.
    """
    # pylint: disable=too-many-branches
    pages: Set[int] = set()

    if not range_str.strip():
        return pages

    parts = range_str.split(",")
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            sub_parts = part.split("-")
            if len(sub_parts) != 2:
                raise ValueError(f"Invalid range format: {part}")
            start_str, end_str = sub_parts[0].strip(), sub_parts[1].strip()
            try:
                start = int(start_str) if start_str else 1
                end = int(end_str) if end_str else max_pages
            except ValueError as err:
                raise ValueError(f"Non-integer in page range: {part}") from err

            if start < 1 or end < 1:
                raise ValueError(f"Page numbers must be positive: {part}")

            # Handle reverse ranges if specified, but standardize to min/max
            actual_start = min(start, end)
            actual_end = max(start, end)

            if actual_start > max_pages:
                continue

            actual_end = min(actual_end, max_pages)
            for page_num in range(actual_start, actual_end + 1):
                pages.add(page_num - 1)
        else:
            try:
                page_num = int(part)
            except ValueError as err:
                raise ValueError(f"Invalid page number: {part}") from err
            if page_num < 1:
                raise ValueError(f"Page numbers must be positive: {part}")
            if page_num <= max_pages:
                pages.add(page_num - 1)

    return pages


def decrypt_pdf_reader(reader: PdfReader, password: str) -> None:
    """Attempt to decrypt a PDF reader if encrypted.

    Args:
        reader: The PdfReader instance.
        password: Password to decrypt.

    Raises:
        ValueError: If PDF is encrypted and decryption failed or no password given.
    """
    if reader.is_encrypted:
        if not password:
            raise ValueError(
                "PDF is encrypted. Please provide a password with --password."
            )
        decrypted = reader.decrypt(password)
        if decrypted == 0:
            raise ValueError("Decryption failed. Incorrect password.")


def handle_merge(inputs: List[Path], output: Path, password: str) -> None:
    """Merge multiple PDF files into one.

    Args:
        inputs: List of Paths to the input PDF files.
        output: Path to the output PDF file.
        password: Password to decrypt encrypted inputs.
    """
    writer = PdfWriter()
    for input_path in inputs:
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        logger.info("Merging file: %s", input_path.as_posix())
        try:
            reader = PdfReader(str(input_path))
            decrypt_pdf_reader(reader, password)
            for page in reader.pages:
                writer.add_page(page)
        except Exception as err:
            raise RuntimeError(f"Failed to read/decrypt {input_path}: {err}") from err

    try:
        with open(output, "wb") as out_file:
            writer.write(out_file)
        logger.info("Merged successfully into: %s", output.as_posix())
    except Exception as err:
        raise RuntimeError(f"Failed to write output PDF: {err}") from err


def handle_split(
    input_path: Path, output_dir: Path, ranges: str, password: str
) -> None:
    """Split a PDF file into separate pages or ranges.

    Args:
        input_path: Path to the input PDF file.
        output_dir: Path to the output directory.
        ranges: Comma-separated page numbers or ranges (e.g. '1-3,5').
        password: Password to decrypt input.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(str(input_path))
    decrypt_pdf_reader(reader, password)
    total_pages = len(reader.pages)

    if ranges:
        target_pages = parse_page_range(ranges, total_pages)
        if not target_pages:
            logger.warning("No valid pages found in range '%s'.", ranges)
            return
        writer = PdfWriter()
        for idx in sorted(target_pages):
            writer.add_page(reader.pages[idx])
        out_name = f"{input_path.stem}_split.pdf"
        out_path = output_dir / out_name
        with open(out_path, "wb") as out_file:
            writer.write(out_file)
        logger.info("Extracted pages %s to: %s", ranges, out_path.as_posix())
    else:
        # Split every page individually
        for idx in range(total_pages):
            writer = PdfWriter()
            writer.add_page(reader.pages[idx])
            out_name = f"{input_path.stem}_page_{idx + 1}.pdf"
            out_path = output_dir / out_name
            with open(out_path, "wb") as out_file:
                writer.write(out_file)
            logger.debug("Saved page %d to: %s", idx + 1, out_path.as_posix())
        logger.info(
            "Split %d pages from %s into %s",
            total_pages,
            input_path.name,
            output_dir.as_posix(),
        )


def handle_rotate(
    input_path: Path, output: Path, angle: int, ranges: str, password: str
) -> None:
    """Rotate all or specific pages in a PDF file.

    Args:
        input_path: Path to the input PDF file.
        output: Path to the output PDF file.
        angle: Angle of rotation clockwise (90, 180, 270).
        ranges: Comma-separated page numbers/ranges to rotate. If empty, rotates all.
        password: Password to decrypt input.
    """
    if angle not in [90, 180, 270]:
        raise ValueError("Rotation angle must be 90, 180, or 270 degrees.")

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    reader = PdfReader(str(input_path))
    decrypt_pdf_reader(reader, password)
    total_pages = len(reader.pages)

    if ranges:
        target_pages = parse_page_range(ranges, total_pages)
    else:
        target_pages = set(range(total_pages))

    writer = PdfWriter()
    for idx in range(total_pages):
        page = reader.pages[idx]
        if idx in target_pages:
            logger.debug("Rotating page %d by %d degrees", idx + 1, angle)
            page.rotate(angle)
        writer.add_page(page)

    with open(output, "wb") as out_file:
        writer.write(out_file)
    logger.info(
        "Rotated specified pages by %d and saved to: %s", angle, output.as_posix()
    )


def handle_extract(input_path: Path, output: Path, ranges: str, password: str) -> None:
    """Extract specific page ranges into a new PDF.

    Args:
        input_path: Path to the input PDF file.
        output: Path to the output PDF file.
        ranges: Comma-separated page numbers or ranges to extract (e.g. '1-3,5').
        password: Password to decrypt input.
    """
    if not ranges:
        raise ValueError("Extract subcommand requires a page range (e.g. --pages 1-3).")

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    reader = PdfReader(str(input_path))
    decrypt_pdf_reader(reader, password)
    total_pages = len(reader.pages)

    target_pages = parse_page_range(ranges, total_pages)
    if not target_pages:
        raise ValueError(f"No pages in PDF matched range '{ranges}'.")

    writer = PdfWriter()
    for idx in sorted(target_pages):
        writer.add_page(reader.pages[idx])

    with open(output, "wb") as out_file:
        writer.write(out_file)
    logger.info("Extracted pages %s to: %s", ranges, output.as_posix())


def handle_compress(input_path: Path, output: Path, password: str) -> None:
    """Compress a PDF file lossless by optimizing streams.

    Args:
        input_path: Path to the input PDF file.
        output: Path to the output PDF file.
        password: Password to decrypt input.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    reader = PdfReader(str(input_path))
    decrypt_pdf_reader(reader, password)
    writer = PdfWriter()

    for idx, page in enumerate(reader.pages):
        logger.debug("Compressing page %d content streams", idx + 1)
        page.compress_content_streams()
        writer.add_page(page)

    with open(output, "wb") as out_file:
        writer.write(out_file)

    orig_size = input_path.stat().st_size
    comp_size = output.stat().st_size
    savings = orig_size - comp_size
    percent = (savings / orig_size * 100) if orig_size > 0 else 0

    logger.info("Original size: %d bytes", orig_size)
    logger.info("Compressed size: %d bytes", comp_size)
    logger.info("Savings: %d bytes (%.2f%%)", savings, percent)


def handle_rename(  # pylint: disable=too-many-locals
    directory: Path, pattern: str, prefix_date: bool, sequential: bool, dry_run: bool
) -> None:
    """Bulk-rename PDFs in a directory.

    Args:
        directory: The directory containing target PDF files.
        pattern: Pattern or text replacement for filenames.
        prefix_date: If True, prefix filename with creation/modification date.
        sequential: If True, number files sequentially.
        dry_run: Preview only. Do not perform rename.
    """
    if not directory.exists() or not directory.is_dir():
        raise ValueError(f"Invalid directory path: {directory}")

    pdf_files = sorted(
        [f for f in directory.iterdir() if f.is_file() and f.suffix.lower() == ".pdf"]
    )
    if not pdf_files:
        logger.info("No PDF files found in directory %s.", directory.as_posix())
        return

    logger.info("Found %d PDF files to rename.", len(pdf_files))
    counter = 1

    for pdf_path in pdf_files:
        stem = pdf_path.stem
        # 1. Apply pattern
        if pattern:
            # If pattern has format old=new
            if "=" in pattern:
                old_txt, new_txt = pattern.split("=", 1)
                stem = stem.replace(old_txt, new_txt)
            else:
                stem = pattern

        # 2. Sequential numbering
        if sequential:
            stem = f"{stem}_{counter:03d}"
            counter += 1

        # 3. Date prefix (using modified time as a portable fallback)
        if prefix_date:
            mtime = pdf_path.stat().st_mtime
            date_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
            stem = f"{date_str}_{stem}"

        new_name = f"{stem}.pdf"
        new_path = pdf_path.parent / new_name

        if new_path != pdf_path:
            # Check for conflict
            if new_path.exists():
                logger.warning(
                    "Rename conflict: %s already exists. Skipping.", new_path.name
                )
                continue
            if dry_run:
                logger.info("[Dry Run] Would rename: %s -> %s", pdf_path.name, new_name)
            else:
                logger.info("Renaming: %s -> %s", pdf_path.name, new_name)
                pdf_path.rename(new_path)


def main() -> None:
    """CLI execution entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "PDF Batch Toolkit — merge, split, rotate, extract, compress, "
            "and rename PDFs."
        )
    )

    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose debug logging."
    )
    parser.add_argument(
        "--password", default="", help="Password for decrypting encrypted PDFs."
    )

    subparsers = parser.add_subparsers(
        dest="command", required=True, help="Subcommands"
    )

    # Merge Subcommand
    merge_parser = subparsers.add_parser("merge", help="Merge multiple PDFs into one.")
    merge_parser.add_argument(
        "-i", "--inputs", nargs="+", required=True, type=Path, help="Input PDF files."
    )
    merge_parser.add_argument(
        "-o", "--output", required=True, type=Path, help="Output PDF file."
    )

    # Split Subcommand
    split_parser = subparsers.add_parser(
        "split", help="Split a PDF into multiple files."
    )
    split_parser.add_argument(
        "-i", "--input", required=True, type=Path, help="Input PDF file."
    )
    split_parser.add_argument(
        "-o", "--output-dir", required=True, type=Path, help="Output directory."
    )
    split_parser.add_argument(
        "-r",
        "--ranges",
        default="",
        help="Page ranges to extract (e.g. '1-3,5'). If omitted, splits every page.",
    )

    # Rotate Subcommand
    rotate_parser = subparsers.add_parser("rotate", help="Rotate PDF pages.")
    rotate_parser.add_argument(
        "-i", "--input", required=True, type=Path, help="Input PDF file."
    )
    rotate_parser.add_argument(
        "-o", "--output", required=True, type=Path, help="Output PDF file."
    )
    rotate_parser.add_argument(
        "-a",
        "--angle",
        required=True,
        type=int,
        choices=[90, 180, 270],
        help="Clockwise rotation angle.",
    )
    rotate_parser.add_argument(
        "-r",
        "--ranges",
        default="",
        help="Page ranges to rotate (e.g. '1-3'). Rotates all pages if omitted.",
    )

    # Extract Subcommand
    extract_parser = subparsers.add_parser(
        "extract", help="Extract page ranges to a new PDF."
    )
    extract_parser.add_argument(
        "-i", "--input", required=True, type=Path, help="Input PDF file."
    )
    extract_parser.add_argument(
        "-o", "--output", required=True, type=Path, help="Output PDF file."
    )
    extract_parser.add_argument(
        "-r", "--ranges", required=True, help="Page ranges to extract (e.g. '1-3,5')."
    )

    # Compress Subcommand
    compress_parser = subparsers.add_parser("compress", help="Compress PDF lossless.")
    compress_parser.add_argument(
        "-i", "--input", required=True, type=Path, help="Input PDF file."
    )
    compress_parser.add_argument(
        "-o", "--output", required=True, type=Path, help="Output PDF file."
    )

    # Rename Subcommand
    rename_parser = subparsers.add_parser(
        "rename", help="Bulk-rename PDFs in a directory."
    )
    rename_parser.add_argument(
        "-d", "--directory", required=True, type=Path, help="Directory containing PDFs."
    )
    rename_parser.add_argument(
        "-p",
        "--pattern",
        default="",
        help="Rename pattern. Use 'old=new' to replace substring, or a plain string.",
    )
    rename_parser.add_argument(
        "--date", action="store_true", help="Prefix filename with date."
    )
    rename_parser.add_argument(
        "--seq", action="store_true", help="Add sequential number suffix."
    )
    rename_parser.add_argument(
        "--dry-run", action="store_true", help="Preview renaming without applying."
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    try:
        if args.command == "merge":
            handle_merge(args.inputs, args.output, args.password)
        elif args.command == "split":
            handle_split(args.input, args.output_dir, args.ranges, args.password)
        elif args.command == "rotate":
            handle_rotate(
                args.input, args.output, args.angle, args.ranges, args.password
            )
        elif args.command == "extract":
            handle_extract(args.input, args.output, args.ranges, args.password)
        elif args.command == "compress":
            handle_compress(args.input, args.output, args.password)
        elif args.command == "rename":
            handle_rename(
                args.directory, args.pattern, args.date, args.seq, args.dry_run
            )
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.error("Error: %s", err)
        sys.exit(1)


if __name__ == "__main__":
    main()
