"""Views and edits PDF metadata (title, author, subject, keywords).

This module displays existing document information dictionary tags from PDF files
and applies metadata edits using pypdf.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import json
import logging
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)


def read_pdf_metadata(pdf_path: Path, password: Optional[str] = None) -> Dict[str, Any]:
    """Read metadata dictionary from a PDF file.

    Args:
        pdf_path: Path to target PDF document.
        password: Optional password for encrypted PDFs.

    Returns:
        Dictionary containing extracted metadata fields.
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
                    "status": "encrypted_password_required",
                }

        raw_meta = reader.metadata
        title = raw_meta.title if raw_meta and raw_meta.title else ""
        author = raw_meta.author if raw_meta and raw_meta.author else ""
        subject = raw_meta.subject if raw_meta and raw_meta.subject else ""
        creator = raw_meta.creator if raw_meta and raw_meta.creator else ""
        producer = raw_meta.producer if raw_meta and raw_meta.producer else ""

        # Extract raw keywords string if present
        keywords = ""
        if raw_meta and "/Keywords" in raw_meta:
            keywords = str(raw_meta["/Keywords"])

        return {
            "file": str(pdf_path),
            "filename": pdf_path.name,
            "title": title,
            "author": author,
            "subject": subject,
            "keywords": keywords,
            "creator": creator,
            "producer": producer,
            "total_pages": len(reader.pages),
            "status": "ok",
        }
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.error("Failed to read metadata from %s: %s", pdf_path, err)
        return {
            "file": str(pdf_path),
            "filename": pdf_path.name,
            "status": f"error: {err}",
        }


def update_pdf_metadata(
    input_path: Path,
    output_path: Path,
    new_metadata: Dict[str, str],
    password: Optional[str] = None,
) -> bool:
    """Update metadata fields in a PDF file and save to output path.

    Args:
        input_path: Source PDF document path.
        output_path: Destination PDF document path.
        new_metadata: Dictionary of metadata key/value pairs to set.
        password: Optional password for encrypted source PDF.

    Returns:
        True if metadata was successfully updated and saved, False otherwise.
    """
    try:
        reader = PdfReader(str(input_path))
        if reader.is_encrypted:
            if password:
                reader.decrypt(password)
            else:
                logger.error("PDF is encrypted but no password was provided.")
                return False

        writer = PdfWriter()

        # Copy existing pages
        for page in reader.pages:
            writer.add_page(page)

        # Merge existing metadata with new updates
        existing_meta = reader.metadata
        combined_meta: Dict[str, Any] = {}

        if existing_meta:
            if existing_meta.title:
                combined_meta["/Title"] = existing_meta.title
            if existing_meta.author:
                combined_meta["/Author"] = existing_meta.author
            if existing_meta.subject:
                combined_meta["/Subject"] = existing_meta.subject
            if existing_meta.creator:
                combined_meta["/Creator"] = existing_meta.creator
            if existing_meta.producer:
                combined_meta["/Producer"] = existing_meta.producer
            if "/Keywords" in existing_meta:
                combined_meta["/Keywords"] = existing_meta["/Keywords"]

        tag_map = {
            "title": "/Title",
            "author": "/Author",
            "subject": "/Subject",
            "keywords": "/Keywords",
            "creator": "/Creator",
            "producer": "/Producer",
        }

        for key, value in new_metadata.items():
            if value is not None and key in tag_map:
                combined_meta[tag_map[key]] = value

        writer.add_metadata(combined_meta)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f_out:
            writer.write(f_out)

        writer.close()
        return True
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.error("Failed to update metadata for %s: %s", input_path.name, err)
        return False


def main(args: Optional[List[str]] = None) -> int:
    """Run CLI entry point for PDF metadata editor tool.

    Args:
        args: Command line argument list.

    Returns:
        Exit code integer (0 for success, non-zero for failure).
    """
    parser = argparse.ArgumentParser(
        description="View and edit PDF metadata (title, author, subject, keywords)."
    )
    parser.add_argument("input_pdf", type=str, help="Source PDF file path.")
    parser.add_argument("--title", type=str, default=None, help="Set PDF title.")
    parser.add_argument("--author", type=str, default=None, help="Set PDF author.")
    parser.add_argument("--subject", type=str, default=None, help="Set PDF subject.")
    parser.add_argument("--keywords", type=str, default=None, help="Set PDF keywords.")
    parser.add_argument("--creator", type=str, default=None, help="Set PDF creator.")
    parser.add_argument("--producer", type=str, default=None, help="Set PDF producer.")
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Destination modified PDF path.",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite input PDF file directly.",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format for view mode (default: table).",
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

    edits: Dict[str, str] = {}
    for tag in ["title", "author", "subject", "keywords", "creator", "producer"]:
        val = getattr(parsed_args, tag)
        if val is not None:
            edits[tag] = val

    if edits:
        # Edit mode
        if parsed_args.in_place:
            target_out = input_path
            with tempfile.NamedTemporaryFile(
                mode="wb", suffix=".pdf", delete=False
            ) as tmp_f:
                tmp_out = Path(tmp_f.name)
            success = update_pdf_metadata(
                input_path, tmp_out, edits, parsed_args.password
            )
            if success:
                shutil.move(str(tmp_out), str(target_out))
                logger.info("Successfully updated metadata in-place: %s", target_out)
                return 0
            if tmp_out.exists():
                tmp_out.unlink()
            return 1

        target_out = (
            Path(parsed_args.output)
            if parsed_args.output
            else input_path.parent / f"{input_path.stem}_meta_updated.pdf"
        )
        success = update_pdf_metadata(
            input_path, target_out, edits, parsed_args.password
        )
        if success:
            logger.info("Updated PDF saved to %s", target_out)
            return 0
        return 1

    # View mode
    meta_info = read_pdf_metadata(input_path, parsed_args.password)
    if parsed_args.format == "json":
        print(json.dumps(meta_info, indent=2))
    else:
        print(f"\nPDF Metadata: {meta_info['filename']}")
        print("-" * 50)
        for k in [
            "title",
            "author",
            "subject",
            "keywords",
            "creator",
            "producer",
            "total_pages",
            "status",
        ]:
            if k in meta_info:
                print(f"{k.capitalize():<15}: {meta_info[k]}")
        print("-" * 50 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
