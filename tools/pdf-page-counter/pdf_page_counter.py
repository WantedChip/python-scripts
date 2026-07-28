"""Reports total page counts for all PDFs in a directory in a summary table.

This module recursively scans directories for PDF documents, extracting page count,
file size, and encryption status metrics using pypdf.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import csv
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pypdf import PdfReader

logger = logging.getLogger(__name__)


def count_pdf_pages(pdf_path: Path, password: Optional[str] = None) -> Dict[str, Any]:
    """Inspect a single PDF file to count its total pages.

    Args:
        pdf_path: Path to target PDF file.
        password: Optional password for encrypted source PDFs.

    Returns:
        Dictionary of PDF page count details.
    """
    size_bytes = pdf_path.stat().st_size
    try:
        reader = PdfReader(str(pdf_path))
        if reader.is_encrypted:
            if password:
                reader.decrypt(password)
            else:
                return {
                    "file": str(pdf_path),
                    "filename": pdf_path.name,
                    "pages": 0,
                    "size_bytes": size_bytes,
                    "encrypted": True,
                    "status": "encrypted_password_required",
                }

        page_count = len(reader.pages)
        return {
            "file": str(pdf_path),
            "filename": pdf_path.name,
            "pages": page_count,
            "size_bytes": size_bytes,
            "encrypted": reader.is_encrypted,
            "status": "ok",
        }
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.debug("Error reading PDF %s: %s", pdf_path, err)
        return {
            "file": str(pdf_path),
            "filename": pdf_path.name,
            "pages": 0,
            "size_bytes": size_bytes,
            "encrypted": False,
            "status": f"error: {err}",
        }


def scan_pdf_directory(
    target_dir: Path, recursive: bool = False, password: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], int, int]:
    """Scan directory for PDF files and aggregate page counts.

    Args:
        target_dir: Directory containing PDF files.
        recursive: Whether to scan subdirectories recursively.
        password: Optional default password for encrypted files.

    Returns:
        Tuple containing list of metadata dicts, total page count, and total size.
    """
    pattern = "**/*.pdf" if recursive else "*.pdf"
    pdf_files = sorted(list(target_dir.glob(pattern)), key=lambda p: p.name.lower())

    results: List[Dict[str, Any]] = []
    total_pages = 0
    total_bytes = 0

    for pdf_file in pdf_files:
        info = count_pdf_pages(pdf_file, password)
        results.append(info)
        total_pages += info["pages"]
        total_bytes += info["size_bytes"]

    return results, total_pages, total_bytes


def main(args: Optional[List[str]] = None) -> int:
    """Run CLI entry point for PDF page counter tool.

    Args:
        args: Command line argument list.

    Returns:
        Exit code integer (0 for success, non-zero for failure).
    """
    parser = argparse.ArgumentParser(
        description="Report total page counts for all PDFs in a directory."
    )
    parser.add_argument(
        "directory", type=str, help="Target directory containing PDF files."
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Scan directory recursively.",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["table", "csv", "json"],
        default="table",
        help="Console output format (default: table).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Output summary report file path.",
    )
    parser.add_argument(
        "-p",
        "--password",
        type=str,
        default=None,
        help="Default password for encrypted PDFs.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging."
    )

    parsed_args = parser.parse_args(args)

    level = logging.DEBUG if parsed_args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    target_dir = Path(parsed_args.directory)
    if not target_dir.exists() or not target_dir.is_dir():
        logger.error("Specified directory does not exist: %s", target_dir)
        return 1

    results, total_pages, total_bytes = scan_pdf_directory(
        target_dir, parsed_args.recursive, parsed_args.password
    )

    if parsed_args.output:
        out_path = Path(parsed_args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.suffix.lower() == ".json":
            summary_data = {
                "total_documents": len(results),
                "total_pages": total_pages,
                "total_bytes": total_bytes,
                "documents": results,
            }
            with open(out_path, "w", encoding="utf-8") as f_out:
                json.dump(summary_data, f_out, indent=2)
        else:
            fieldnames = [
                "filename",
                "pages",
                "size_bytes",
                "encrypted",
                "status",
                "file",
            ]
            with open(out_path, "w", newline="", encoding="utf-8") as f_csv:
                writer = csv.DictWriter(
                    f_csv, fieldnames=fieldnames, extrasaction="ignore"
                )
                writer.writeheader()
                writer.writerows(results)
        logger.info("Summary report exported to %s", out_path)

    if parsed_args.format == "json":
        summary_data = {
            "total_documents": len(results),
            "total_pages": total_pages,
            "total_bytes": total_bytes,
            "documents": results,
        }
        print(json.dumps(summary_data, indent=2))
    elif parsed_args.format == "csv":
        fieldnames = ["filename", "pages", "size_bytes", "status"]
        writer = csv.DictWriter(
            sys.stdout, fieldnames=fieldnames, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(results)
    else:  # table
        print(f"\nPDF Page Count Summary ({len(results)} files found)")
        print("-" * 65)
        hdr = (
            f"{'Filename':<32} | {'Pages':<8} | {'Size (KB)':<10} | " f"{'Status':<10}"
        )
        print(hdr)
        print("-" * 65)
        for item in results:
            fname = (
                item["filename"][:29] + "..."
                if len(item["filename"]) > 32
                else item["filename"]
            )
            kb_size = round(item["size_bytes"] / 1024.0, 1)
            print(
                f"{fname:<32} | {item['pages']:<8} | {kb_size:<10} | "
                f"{item['status']:<10}"
            )
        print("-" * 65)
        total_mb = round(total_bytes / (1024 * 1024), 2)
        print(
            f"Total Documents: {len(results)} | Total Pages: {total_pages} | "
            f"Total Size: {total_mb} MB\n"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
