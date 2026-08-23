"""Convert color images to grayscale in bulk with contrast and brightness tuning.

This module converts color photos to 8-bit grayscale images supporting contrast
enhancement factors, brightness adjustment, and optional sepia tone filtering.
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
    from PIL import Image, ImageEnhance

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}


def convert_to_grayscale(
    input_file: Path,
    output_file: Path,
    contrast_factor: float = 1.0,
    brightness_factor: float = 1.0,
    sepia: bool = False,
    quality: int = 90,
) -> bool:
    """Convert a single image file to grayscale or sepia tone.

    Args:
        input_file: Source image file path.
        output_file: Target output image file path.
        contrast_factor: Multiplier factor for contrast enhancement (default: 1.0).
        brightness_factor: Multiplier factor for brightness (default: 1.0).
        sepia: Apply vintage sepia tone filter.
        quality: JPEG/WebP quality rating (1-100).

    Returns:
        True if conversion succeeded, False otherwise.
    """
    if not HAS_PIL:
        logger.error("Pillow package is required.")
        return False

    try:
        with Image.open(input_file) as img:
            gray_img = img.convert("L")

            if contrast_factor != 1.0:
                contrast_enhancer = ImageEnhance.Contrast(gray_img)
                gray_img = contrast_enhancer.enhance(contrast_factor)

            if brightness_factor != 1.0:
                bright_enhancer = ImageEnhance.Brightness(gray_img)
                gray_img = bright_enhancer.enhance(brightness_factor)

            if sepia:
                # Convert grayscale to sepia RGB tint
                rgb_img = gray_img.convert("RGB")
                pixels = list(rgb_img.getdata())
                sepia_pixels = []
                for r, g, b in pixels:
                    # Use standard sepia transformation
                    sr = int(r * 0.393 + g * 0.769 + b * 0.189)
                    sg = int(r * 0.349 + g * 0.686 + b * 0.168)
                    sb = int(r * 0.272 + g * 0.534 + b * 0.131)
                    sepia_pixels.append((min(255, sr), min(255, sg), min(255, sb)))
                out_img: Image.Image = Image.new("RGB", gray_img.size)
                out_img.putdata(sepia_pixels)
            else:
                out_img = gray_img

            output_file.parent.mkdir(parents=True, exist_ok=True)
            if output_file.suffix.lower() in (".jpg", ".jpeg"):
                out_img.save(output_file, "JPEG", quality=quality, optimize=True)
            else:
                out_img.save(output_file)

            logger.info(
                "Converted to grayscale: %s -> %s",
                input_file.name,
                output_file.name,
            )
            return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed converting %s to grayscale: %s", input_file, exc)
        return False


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description="Convert color images to grayscale in bulk with contrast tuning."
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
        "-c",
        "--contrast",
        type=float,
        default=1.0,
        help="Contrast multiplier factor (default: 1.0).",
    )
    parser.add_argument(
        "-b",
        "--brightness",
        type=float,
        default=1.0,
        help="Brightness multiplier factor (default: 1.0).",
    )
    parser.add_argument(
        "--sepia",
        action="store_true",
        help="Apply vintage sepia tone filter instead of pure grayscale.",
    )
    parser.add_argument(
        "--suffix",
        type=str,
        default="_gray",
        help="Filename suffix for converted images (default: '_gray').",
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
        logger.warning("No supported image files found to convert.")
        return 0

    out_dir = Path(parsed_args.output) if parsed_args.output else input_path.parent
    if input_path.is_dir() and not parsed_args.output:
        out_dir = input_path

    success_cnt = 0
    for src in image_files:
        rel = src.relative_to(input_path) if input_path.is_dir() else Path(src.name)
        dst = out_dir / rel.parent / f"{rel.stem}{parsed_args.suffix}{rel.suffix}"

        ok = convert_to_grayscale(
            src,
            dst,
            contrast_factor=parsed_args.contrast,
            brightness_factor=parsed_args.brightness,
            sepia=parsed_args.sepia,
            quality=parsed_args.quality,
        )
        if ok:
            success_cnt += 1

    logger.info(
        "Successfully converted %d/%d images to grayscale.",
        success_cnt,
        len(image_files),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
