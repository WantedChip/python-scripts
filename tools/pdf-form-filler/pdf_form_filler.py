"""Fills PDF form fields programmatically using a JSON data file.

This module inspects AcroForm interactive form fields in PDF documents using pypdf,
dumps field names, and applies JSON field value mapping to output filled PDFs.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-return-statements,broad-exception-caught

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)


def inspect_form_fields(
    input_pdf: Path, password: Optional[str] = None
) -> Dict[str, Any]:
    """Inspect and extract interactive form field names and details.

    Args:
        input_pdf: Path to source PDF file.
        password: Optional password for encrypted source PDF.

    Returns:
        Dictionary of field names, field types, and current values.
    """
    try:
        reader = PdfReader(str(input_pdf))
        if reader.is_encrypted:
            if password:
                reader.decrypt(password)
            else:
                return {
                    "file": str(input_pdf),
                    "fields": {},
                    "status": "encrypted_password_required",
                }

        fields_dict: Dict[str, Any] = {}
        raw_fields = reader.get_fields()
        if raw_fields:
            for field_name, field_data in raw_fields.items():
                val = field_data.get("/V", "")
                f_type = field_data.get("/FT", "Unknown")
                fields_dict[field_name] = {
                    "type": str(f_type),
                    "value": str(val) if val is not None else "",
                }

        return {
            "file": str(input_pdf),
            "filename": input_pdf.name,
            "field_count": len(fields_dict),
            "fields": fields_dict,
            "status": "ok",
        }
    except Exception as err:
        logger.error("Failed to inspect form fields in %s: %s", input_pdf, err)
        return {
            "file": str(input_pdf),
            "filename": input_pdf.name,
            "field_count": 0,
            "fields": {},
            "status": f"error: {err}",
        }


def fill_pdf_form(
    input_pdf: Path,
    output_pdf: Path,
    data_values: Dict[str, str],
    password: Optional[str] = None,
) -> bool:
    """Fill PDF form field values and save to destination path.

    Args:
        input_pdf: Path to source PDF form.
        output_pdf: Path to output filled PDF file.
        data_values: Dictionary mapping field names to value strings.
        password: Optional password for encrypted source PDF.

    Returns:
        True if form filling succeeded, False otherwise.
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

        for page in writer.pages:
            try:
                writer.update_page_form_field_values(page, data_values)
            except Exception as page_err:
                logger.debug(
                    "Page form update notification for %s: %s",
                    input_pdf.name,
                    page_err,
                )

        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        with open(output_pdf, "wb") as f_out:
            writer.write(f_out)

        writer.close()
        return True
    except Exception as err:
        logger.error("Failed to fill PDF form %s: %s", input_pdf.name, err)
        return False


def main(args: Optional[List[str]] = None) -> int:
    """Run CLI entry point for PDF form filler tool.

    Args:
        args: Command line argument list.

    Returns:
        Exit code integer (0 for success, non-zero for failure).
    """
    parser = argparse.ArgumentParser(
        description="Fill PDF form fields programmatically using a JSON data file."
    )
    parser.add_argument("input_pdf", type=str, help="Source PDF form path.")
    parser.add_argument(
        "-d",
        "--data",
        type=str,
        default=None,
        help="JSON file containing field name/value mapping.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Destination filled output PDF path.",
    )
    parser.add_argument(
        "--dump-fields",
        action="store_true",
        help="Dump interactive form field names and exit.",
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

    if parsed_args.dump_fields:
        info = inspect_form_fields(input_path, parsed_args.password)
        print(json.dumps(info, indent=2))
        return 0

    if not parsed_args.data:
        logger.error("Must specify data JSON file (-d/--data) or --dump-fields flag.")
        return 1

    data_path = Path(parsed_args.data)
    if not data_path.exists() or not data_path.is_file():
        logger.error("JSON data file does not exist: %s", data_path)
        return 1

    try:
        with open(data_path, "r", encoding="utf-8") as f_json:
            field_data = json.load(f_json)
    except Exception as err:
        logger.error("Failed to parse JSON data file: %s", err)
        return 1

    if not isinstance(field_data, dict):
        logger.error("JSON data file must contain a top-level dictionary object.")
        return 1

    string_data = {str(k): str(v) for k, v in field_data.items()}

    out_path = (
        Path(parsed_args.output)
        if parsed_args.output
        else input_path.parent / f"{input_path.stem}_filled.pdf"
    )

    logger.info("Filling form fields into %s...", out_path.name)
    if fill_pdf_form(input_path, out_path, string_data, parsed_args.password):
        logger.info("Successfully exported filled PDF to %s", out_path)
        return 0

    logger.error("Failed to export filled PDF.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
