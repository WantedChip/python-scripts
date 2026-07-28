"""Remove EXIF metadata, IPTC headers, and GPS location data from images for privacy.

This module strips sensitive EXIF headers, camera settings, and geotags from
photos before sharing while optionally keeping EXIF orientation formatting intact.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

try:
    from PIL import Image, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tiff"}


def strip_metadata(
    image_path: Path,
    output_path: Path,
    preserve_orientation: bool = True,
) -> bool:
    """Remove all metadata from an image file and save clean copy.

    Args:
        image_path: Path to original source image file.
        output_path: Path to write metadata-stripped image.
        preserve_orientation: Auto-orient image pixels based on EXIF before stripping.

    Returns:
        True if successfully stripped and saved, False otherwise.
    """
    if not HAS_PIL:
        logger.error("Pillow package is required.")
        return False

    try:
        with Image.open(image_path) as img:
            if preserve_orientation:
                try:
                    img = ImageOps.exif_transpose(img)
                except Exception:  # pylint: disable=broad-exception-caught # nosec B110
                    pass

            # Create clean copy of pixel data without EXIF info dictionary
            data = list(img.getdata())
            clean_img = Image.new(img.mode, img.size)
            clean_img.putdata(data)  # type: ignore[no-untyped-call]

            output_path.parent.mkdir(parents=True, exist_ok=True)
            if output_path.suffix.lower() in (".jpg", ".jpeg"):
                if clean_img.mode in ("RGBA", "P"):
                    clean_img = clean_img.convert("RGB")
                clean_img.save(output_path, "JPEG", quality=95, optimize=True)
            else:
                clean_img.save(output_path)

            logger.info(
                "Stripped metadata: %s -> %s",
                image_path.name,
                output_path.name,
            )
            return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed to strip metadata from %s: %s", image_path, exc)
        return False


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description="Remove EXIF metadata and GPS tags from images for privacy."
    )
    parser.add_argument(
        "input",
        type=str,
        help="Input image file or directory path.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Output directory path. Defaults to input location.",
    )
    parser.add_argument(
        "--suffix",
        type=str,
        default="_clean",
        help="Filename suffix for clean output files (default: '_clean').",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite original source files in-place with clean versions.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable detailed debug logging.",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint.

    Args:
        args: Argument list or None for sys.argv[1:].

    Returns:
        Exit code integer (0 for success, non-zero for error).
    """
    parser = setup_cli_parser()
    parsed_args = parser.parse_args(args)

    log_level = logging.DEBUG if parsed_args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    if not HAS_PIL:
        logger.error("Pillow library is required. Install via: pip install Pillow")
        return 1

    input_path = Path(parsed_args.input)
    if not input_path.exists():
        logger.error("Input path does not exist: %s", input_path)
        return 1

    image_files: List[Path] = []
    if input_path.is_file():
        image_files.append(input_path)
    elif input_path.is_dir():
        for root, _, filenames in os.walk(input_path):
            for fname in filenames:
                p = Path(root) / fname
                if p.suffix.lower() in SUPPORTED_EXTENSIONS:
                    image_files.append(p)

    if not image_files:
        logger.warning("No supported image files found to strip.")
        return 0

    out_dir = Path(parsed_args.output) if parsed_args.output else input_path.parent
    if input_path.is_dir() and not parsed_args.output:
        out_dir = input_path

    success_cnt = 0
    for src in image_files:
        if parsed_args.in_place:
            dst = src
        else:
            rel = (
                src.relative_to(input_path)
                if input_path.is_dir()
                else Path(src.name)
            )
            dst = out_dir / rel.parent / f"{rel.stem}{parsed_args.suffix}{rel.suffix}"

        ok = strip_metadata(src, dst)
        if ok:
            success_cnt += 1

    logger.info(
        "Successfully stripped metadata from %d/%d images.",
        success_cnt,
        len(image_files),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
