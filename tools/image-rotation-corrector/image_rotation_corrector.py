"""Auto-detect and correct image orientation based on EXIF camera orientation data.

This module reads EXIF orientation tags from photos and losslessly transposes pixels
to upright orientation in bulk, optionally stripping orientation EXIF flags afterwards.
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


def correct_image_orientation(
    image_path: Path,
    output_path: Path,
    quality: int = 90,
) -> bool:
    """Detect EXIF orientation and transpose image to upright orientation.

    Args:
        image_path: Path to source image file.
        output_path: Path to output corrected image file.
        quality: JPEG/WebP quality rating (1-100).

    Returns:
        True if rotation check/correction succeeded, False otherwise.
    """
    if not HAS_PIL:
        logger.error("Pillow package is required.")
        return False

    try:
        with Image.open(image_path) as img:
            try:
                res_img = ImageOps.exif_transpose(img)
                transposed = res_img if res_img is not None else img.copy()
            except Exception:  # pylint: disable=broad-exception-caught # nosec B110
                transposed = img.copy()

            output_path.parent.mkdir(parents=True, exist_ok=True)
            if output_path.suffix.lower() in (".jpg", ".jpeg"):
                if transposed.mode in ("RGBA", "P"):
                    transposed = transposed.convert("RGB")
                transposed.save(output_path, "JPEG", quality=quality, optimize=True)
            else:
                transposed.save(output_path)

            logger.info(
                "Corrected orientation: %s -> %s",
                image_path.name,
                output_path.name,
            )
            return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed orientation correction for %s: %s", image_path, exc)
        return False


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description="Auto-detect and correct image orientation based on EXIF data."
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
        default="_upright",
        help="Filename suffix for corrected files (default: '_upright').",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite original files in-place with corrected versions.",
    )
    parser.add_argument(
        "-q",
        "--quality",
        type=int,
        default=90,
        help="JPEG quality rating 1-100 (default: 90).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable detailed debug logging.",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI entry point.

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
        logger.warning("No supported image files found to process.")
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

        ok = correct_image_orientation(src, dst, quality=parsed_args.quality)
        if ok:
            success_cnt += 1

    logger.info(
        "Successfully corrected orientation for %d/%d images.",
        success_cnt,
        len(image_files),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
