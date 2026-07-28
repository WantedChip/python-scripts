"""Removes password protection from PDFs given the owner/user password.

This module decrypts password-protected PDF files using pypdf and outputs
unencrypted PDF documents for unhindered viewing and printing.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)


def remove_pdf_password(
    input_file: Path, output_file: Path, password: Optional[str] = None
) -> bool:
    """Decrypt a password-protected PDF file and save an unencrypted copy.

    Args:
        input_file: Path to source PDF file.
        output_file: Target destination unencrypted PDF file path.
        password: Owner or user password string.

    Returns:
        True if decryption and writing succeeded, False otherwise.
    """
    try:
        reader = PdfReader(str(input_file))

        if reader.is_encrypted:
            if not password:
                logger.error(
                    "PDF %s is password-protected but no password was provided.",
                    input_file.name,
                )
                return False

            decrypt_res = reader.decrypt(password)
            if decrypt_res == 0:
                logger.error(
                    "Failed to decrypt PDF %s: Incorrect password.", input_file.name
                )
                return False

        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "wb") as f_out:
            writer.write(f_out)

        writer.close()
        return True
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.error("Failed to remove password from %s: %s", input_file.name, err)
        return False


def main(args: Optional[List[str]] = None) -> int:
    """Run CLI entry point for PDF password remover tool.

    Args:
        args: Command line argument list.

    Returns:
        Exit code integer (0 for success, non-zero for failure).
    """
    parser = argparse.ArgumentParser(
        description="Remove password protection from PDFs given the password."
    )
    parser.add_argument(
        "input_pdf", type=str, help="Source PDF file path or directory."
    )
    parser.add_argument(
        "-p",
        "--password",
        type=str,
        default=None,
        help="Owner or user password required for decryption.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Destination decrypted output PDF path or directory.",
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
        logger.error("No PDF files found at target path.")
        return 1

    success_count = 0

    for pdf_file in pdf_files:
        if parsed_args.output:
            out_path = Path(parsed_args.output)
            if len(pdf_files) == 1 and not out_path.is_dir():
                target_out = out_path
            else:
                out_path.mkdir(parents=True, exist_ok=True)
                target_out = out_path / f"{pdf_file.stem}_unlocked.pdf"
        else:
            target_out = pdf_file.parent / f"{pdf_file.stem}_unlocked.pdf"

        logger.info("Decrypting %s -> %s...", pdf_file.name, target_out.name)
        if remove_pdf_password(pdf_file, target_out, parsed_args.password):
            success_count += 1

    if success_count > 0:
        logger.info("Successfully decrypted %d PDF files.", success_count)
        return 0

    logger.error("Failed to decrypt any PDF files.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
