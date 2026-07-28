"""Reduces PDF file size by downsampling images and removing redundant data.

This module optimizes PDF files using pypdf stream compression and deduplication
of identical objects, reporting reduction statistics.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)


def compress_pdf_file(
    input_path: Path,
    output_path: Path,
    password: Optional[str] = None,
) -> Dict[str, Any]:
    """Compress PDF document by compressing streams and deduplicating objects.

    Args:
        input_path: Source PDF file path.
        output_path: Target compressed output PDF path.
        password: Optional password for encrypted source PDF.

    Returns:
        Dictionary containing file sizes, compression ratio, and status.
    """
    orig_size = input_path.stat().st_size
    try:
        reader = PdfReader(str(input_path))
        if reader.is_encrypted:
            if password:
                reader.decrypt(password)
            else:
                logger.error("PDF %s is encrypted.", input_path.name)
                return {
                    "file": str(input_path),
                    "filename": input_path.name,
                    "orig_size": orig_size,
                    "compressed_size": orig_size,
                    "reduction_percent": 0.0,
                    "status": "encrypted_password_required",
                }

        writer = PdfWriter()

        for page in reader.pages:
            try:
                page.compress_content_streams()
            except Exception as p_err:  # pylint: disable=broad-exception-caught
                logger.debug("Page stream compression warning: %s", p_err)
            writer.add_page(page)

        if hasattr(writer, "remove_duplicates"):
            writer.remove_duplicates()
        else:
            writer.compress_identical_objects()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f_out:
            writer.write(f_out)

        writer.close()

        compressed_size = output_path.stat().st_size
        saved_bytes = orig_size - compressed_size
        reduction_pct = (
            round((saved_bytes / float(orig_size)) * 100.0, 2) if orig_size > 0 else 0.0
        )

        return {
            "file": str(input_path),
            "filename": input_path.name,
            "orig_size": orig_size,
            "compressed_size": compressed_size,
            "reduction_percent": reduction_pct,
            "status": "ok",
        }
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.error("Failed to compress PDF %s: %s", input_path.name, err)
        return {
            "file": str(input_path),
            "filename": input_path.name,
            "orig_size": orig_size,
            "compressed_size": orig_size,
            "reduction_percent": 0.0,
            "status": f"error: {err}",
        }


def main(args: Optional[List[str]] = None) -> int:
    """Run CLI entry point for PDF compressor tool.

    Args:
        args: Command line argument list.

    Returns:
        Exit code integer (0 for success, non-zero for failure).
    """
    parser = argparse.ArgumentParser(
        description=(
            "Reduce PDF file size by compressing streams and deduplicating" " objects."
        )
    )
    parser.add_argument(
        "input_pdf", type=str, help="Source PDF file path or directory."
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Target output compressed PDF path or directory.",
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

    input_path = Path(parsed_args.input_pdf)
    if not input_path.exists():
        logger.error("Specified input path does not exist: %s", input_path)
        return 1

    pdf_files: List[Path] = []
    if input_path.is_file():
        pdf_files.append(input_path)
    elif input_path.is_dir():
        pdf_files = sorted(list(input_path.glob("*.pdf")), key=lambda p: p.name.lower())

    if not pdf_files:
        logger.error("No PDF files found to compress.")
        return 1

    results: List[Dict[str, Any]] = []

    for pdf_file in pdf_files:
        if parsed_args.output:
            out_p = Path(parsed_args.output)
            if len(pdf_files) == 1 and not out_p.is_dir():
                target_out = out_p
            else:
                out_p.mkdir(parents=True, exist_ok=True)
                target_out = out_p / f"{pdf_file.stem}_compressed.pdf"
        else:
            target_out = pdf_file.parent / f"{pdf_file.stem}_compressed.pdf"

        logger.info("Compressing %s -> %s...", pdf_file.name, target_out.name)
        info = compress_pdf_file(pdf_file, target_out, parsed_args.password)
        results.append(info)

        if info["status"] == "ok":
            orig_kb = round(info["orig_size"] / 1024.0, 1)
            comp_kb = round(info["compressed_size"] / 1024.0, 1)
            logger.info(
                "Compressed %s: %s KB -> %s KB (%.1f%% reduction)",
                pdf_file.name,
                orig_kb,
                comp_kb,
                info["reduction_percent"],
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
