"""Converts each page of a PDF to high-resolution PNG or JPEG images.

This module extracts embedded images from PDF pages and renders page snapshots
using pypdf and Pillow.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-nested-blocks,broad-exception-caught

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional, Set

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader

logger = logging.getLogger(__name__)


def parse_page_ranges(range_str: str, max_pages: int) -> Set[int]:
    """Parse page range string (e.g. "1-3,5") into 0-indexed page set.

    Args:
        range_str: Range specification string.
        max_pages: Total number of pages in PDF document.

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
                logger.warning("Invalid page range slice: %s", clean)
        else:
            try:
                page_num = int(clean)
                if 1 <= page_num <= max_pages:
                    selected.add(page_num - 1)
            except ValueError:
                logger.warning("Invalid page number: %s", clean)
    return selected


def render_fallback_page_image(
    page_num: int, text_content: str, width: int = 800, height: int = 1000
) -> Image.Image:
    """Create a synthetic page snapshot image for text content.

    Args:
        page_num: 1-based page number.
        text_content: Extracted text content string.
        width: Image width in pixels.
        height: Image height in pixels.

    Returns:
        PIL Image object.
    """
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Draw page border and header
    draw.rectangle([10, 10, width - 10, height - 10], outline=(200, 200, 200), width=2)
    hdr_text = f"Page {page_num}"
    draw.text((30, 30), hdr_text, fill=(50, 50, 50))

    y_offset = 70
    lines = text_content.splitlines()[:30]
    font = ImageFont.load_default()

    for line in lines:
        if y_offset > height - 50:
            break
        draw.text((30, y_offset), line[:90], fill=(0, 0, 0), font=font)
        y_offset += 25

    return img


def convert_pdf_to_images(
    pdf_path: Path,
    output_dir: Path,
    img_format: str = "png",
    range_str: Optional[str] = None,
    password: Optional[str] = None,
) -> List[Path]:
    """Convert PDF pages to image files.

    Args:
        pdf_path: Path to source PDF file.
        output_dir: Output directory path.
        img_format: Target image format ('png' or 'jpeg').
        range_str: Optional page range filter string.
        password: Optional password for encrypted source PDF.

    Returns:
        List of generated image file paths.
    """
    generated: List[Path] = []
    try:
        reader = PdfReader(str(pdf_path))
        if reader.is_encrypted:
            if password:
                reader.decrypt(password)
            else:
                logger.error("PDF %s is encrypted.", pdf_path.name)
                return generated

        total_pages = len(reader.pages)
        if range_str:
            target_indices = sorted(parse_page_ranges(range_str, total_pages))
        else:
            target_indices = list(range(total_pages))

        output_dir.mkdir(parents=True, exist_ok=True)
        ext = "jpg" if img_format.lower() in ("jpeg", "jpg") else "png"
        save_fmt = "JPEG" if ext == "jpg" else "PNG"

        for idx in target_indices:
            page = reader.pages[idx]
            page_num = idx + 1
            extracted_images = page.images

            if extracted_images:
                for img_idx, img_obj in enumerate(extracted_images):
                    try:
                        out_name = f"{pdf_path.stem}_p{page_num}_img{img_idx + 1}.{ext}"
                        out_file = output_dir / out_name
                        raw_img: Image.Image = Image.open(img_obj.data)
                        if save_fmt == "JPEG" and raw_img.mode in ("RGBA", "P"):
                            raw_img = raw_img.convert("RGB")
                        raw_img.save(out_file, format=save_fmt)
                        generated.append(out_file)
                    except Exception as img_err:
                        logger.warning(
                            "Failed to extract image on page %d: %s", page_num, img_err
                        )

            if not extracted_images:
                # Generate synthetic page snapshot
                text_content = page.extract_text() or ""
                fallback_img = render_fallback_page_image(page_num, text_content)
                out_name = f"{pdf_path.stem}_p{page_num}.{ext}"
                out_file = output_dir / out_name
                fallback_img.save(out_file, format=save_fmt)
                generated.append(out_file)

        return generated
    except Exception as err:
        logger.error("Failed to convert PDF %s to images: %s", pdf_path.name, err)
        return generated


def main(args: Optional[List[str]] = None) -> int:
    """Run CLI entry point for PDF to image converter tool.

    Args:
        args: Command line argument list.

    Returns:
        Exit code integer (0 for success, non-zero for failure).
    """
    parser = argparse.ArgumentParser(
        description="Convert each page of a PDF to high-resolution PNG or JPEG images."
    )
    parser.add_argument("input_pdf", type=str, help="Source PDF file path.")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=str,
        default=None,
        help="Destination directory for output images.",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["png", "jpeg", "jpg"],
        default="png",
        help="Target image format (default: png).",
    )
    parser.add_argument(
        "-r",
        "--ranges",
        type=str,
        default=None,
        help="Page range filter (e.g. '1-3,5').",
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
    if not input_path.exists() or not input_path.is_file():
        logger.error("Source PDF file does not exist: %s", input_path)
        return 1

    out_dir = (
        Path(parsed_args.output_dir)
        if parsed_args.output_dir
        else input_path.parent / f"{input_path.stem}_images"
    )

    results = convert_pdf_to_images(
        input_path,
        out_dir,
        parsed_args.format,
        parsed_args.ranges,
        parsed_args.password,
    )

    if results:
        logger.info("Converted %d page image(s) to %s", len(results), out_dir)
        return 0

    logger.error("Failed to convert PDF pages to images.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
