"""Convert image files between formats in bulk with RGBA flattening options.

This module provides batch image format conversion (JPEG, PNG, WebP, BMP, TIFF)
handling transparency flattening, quality settings, and recursive directory scans.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

try:
    from PIL import Image

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = {
    "jpg": ".jpg",
    "jpeg": ".jpeg",
    "png": ".png",
    "webp": ".webp",
    "bmp": ".bmp",
    "tiff": ".tiff",
}

TupleRGB = Tuple[int, int, int]


def parse_hex_color(hex_str: str) -> TupleRGB:
    """Parse hex string to RGB tuple.

    Args:
        hex_str: Color string like '#FFFFFF' or 'white'.

    Returns:
        Tuple of (R, G, B) integers.
    """
    cleaned = hex_str.lstrip("#").lower()
    if cleaned == "white" or len(cleaned) != 6:
        return (255, 255, 255)
    try:
        r = int(cleaned[0:2], 16)
        g = int(cleaned[2:4], 16)
        b = int(cleaned[4:6], 16)
        return (r, g, b)
    except ValueError:
        return (255, 255, 255)


def convert_image_format(
    input_file: Path,
    output_file: Path,
    target_format: str,
    quality: int = 90,
    bg_color: TupleRGB = (255, 255, 255),
    remove_source: bool = False,
) -> bool:
    """Convert a single image file to the target format.

    Args:
        input_file: Path to source image file.
        output_file: Target output image path.
        target_format: Target format extension ('png', 'jpeg', 'webp', etc.).
        quality: Image quality compression (1-100).
        bg_color: Background RGB tuple when flattening RGBA to JPEG.
        remove_source: Whether to delete the original source file.

    Returns:
        True if conversion succeeded, False otherwise.
    """
    if not HAS_PIL:
        logger.error("Pillow package is required.")
        return False

    fmt_lower = target_format.lower().lstrip(".")
    if fmt_lower not in SUPPORTED_FORMATS:
        logger.error("Unsupported target format: %s", target_format)
        return False

    try:
        with Image.open(input_file) as img:
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Flatten alpha channel if converting RGBA to JPEG/BMP
            if fmt_lower in ("jpg", "jpeg", "bmp") and img.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", img.size, bg_color)
                if img.mode == "P":
                    img = img.convert("RGBA")
                if img.mode in ("RGBA", "LA"):
                    background.paste(img, mask=img.split()[-1])
                converted_img = background
            else:
                converted_img = img

            save_kwargs = {}
            if fmt_lower in ("jpg", "jpeg", "webp"):
                save_kwargs["quality"] = quality
                save_kwargs["optimize"] = True

            pil_format = "JPEG" if fmt_lower in ("jpg", "jpeg") else fmt_lower.upper()
            converted_img.save(output_file, format=pil_format, **save_kwargs)

            if remove_source and input_file.resolve() != output_file.resolve():
                input_file.unlink()

            logger.info("Converted %s -> %s", input_file.name, output_file.name)
            return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed converting %s: %s", input_file, exc)
        return False


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description="Convert images between formats (JPEG, PNG, WebP, BMP, TIFF)."
    )
    parser.add_argument(
        "input",
        type=str,
        help="Input image file or directory path.",
    )
    parser.add_argument(
        "-f",
        "--format",
        required=True,
        choices=list(SUPPORTED_FORMATS.keys()),
        help="Target output format (e.g. png, jpg, webp).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Output directory path. Defaults to input location.",
    )
    parser.add_argument(
        "-q",
        "--quality",
        type=int,
        default=90,
        help="Output quality 1-100 for JPEG/WebP (default: 90).",
    )
    parser.add_argument(
        "--bg-color",
        type=str,
        default="#FFFFFF",
        help="Background hex color for RGBA transparency flattening.",
    )
    parser.add_argument(
        "--remove-source",
        action="store_true",
        help="Delete original source files after successful conversion.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable detailed debug logging.",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI execution entry point.

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

    bg_rgb = parse_hex_color(parsed_args.bg_color)
    target_ext = SUPPORTED_FORMATS[parsed_args.format.lower()]

    files_to_process: List[Path] = []
    if input_path.is_file():
        files_to_process.append(input_path)
    elif input_path.is_dir():
        for root, _, filenames in os.walk(input_path):
            for fname in filenames:
                p = Path(root) / fname
                if p.suffix.lower() in SUPPORTED_FORMATS.values():
                    files_to_process.append(p)

    if not files_to_process:
        logger.warning("No supported image files found to convert.")
        return 0

    out_dir = Path(parsed_args.output) if parsed_args.output else input_path.parent
    if input_path.is_dir() and not parsed_args.output:
        out_dir = input_path

    success_cnt = 0
    for src in files_to_process:
        rel = src.relative_to(input_path) if input_path.is_dir() else Path(src.name)
        dst = out_dir / rel.parent / f"{rel.stem}{target_ext}"

        ok = convert_image_format(
            src,
            dst,
            target_format=parsed_args.format,
            quality=parsed_args.quality,
            bg_color=bg_rgb,
            remove_source=parsed_args.remove_source,
        )
        if ok:
            success_cnt += 1

    logger.info(
        "Successfully converted %d/%d images.",
        success_cnt,
        len(files_to_process),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
