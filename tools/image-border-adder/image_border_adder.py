"""Add decorative borders, padded matting frames, or polaroid borders to images.

This module expands image canvases to add colored borders, matting padding, or
customizable polaroid-style bottom borders for social media publishing.
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
    from PIL import Image, ImageOps

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}

TupleRGB = Tuple[int, int, int]


def parse_hex_color(hex_str: str) -> TupleRGB:
    """Parse hex color string to RGB tuple.

    Args:
        hex_str: Color string (e.g., '#FFFFFF' or 'black').

    Returns:
        RGB integer tuple.
    """
    cleaned = hex_str.lstrip("#").lower()
    if cleaned == "black":
        return (0, 0, 0)
    if cleaned in ("white", "") or len(cleaned) != 6:
        return (255, 255, 255)
    try:
        r = int(cleaned[0:2], 16)
        g = int(cleaned[2:4], 16)
        b = int(cleaned[4:6], 16)
        return (r, g, b)
    except ValueError:
        return (255, 255, 255)


def add_image_border(
    image_path: Path,
    output_path: Path,
    border_width: int = 20,
    border_color: TupleRGB = (255, 255, 255),
    polaroid: bool = False,
    bottom_margin: int = 60,
    quality: int = 90,
) -> bool:
    """Add a colored border or polaroid matted frame around an image.

    Args:
        image_path: Path to input image file.
        output_path: Output image file path.
        border_width: Border width in pixels for top/left/right/bottom sides.
        border_color: Border RGB color tuple.
        polaroid: If True, extends bottom margin for polaroid frame style.
        bottom_margin: Extra bottom margin in pixels for polaroid mode.
        quality: JPEG/WebP quality rating (1-100).

    Returns:
        True if border was added successfully, False otherwise.
    """
    if not HAS_PIL:
        logger.error("Pillow package is required.")
        return False

    try:
        with Image.open(image_path) as img:
            base_img = img.convert("RGB") if img.mode != "RGB" else img

            if polaroid:
                # Top, left, right get border_width; bottom gets width + bottom_margin
                b_top = border_width
                b_left = border_width
                b_right = border_width
                b_bottom = border_width + bottom_margin

                new_w = base_img.width + b_left + b_right
                new_h = base_img.height + b_top + b_bottom

                bordered = Image.new("RGB", (new_w, new_h), border_color)
                bordered.paste(base_img, (b_left, b_top))
            else:
                bordered = ImageOps.expand(
                    base_img,
                    border=border_width,
                    fill=border_color,
                )

            output_path.parent.mkdir(parents=True, exist_ok=True)
            if output_path.suffix.lower() in (".jpg", ".jpeg"):
                bordered.save(output_path, "JPEG", quality=quality, optimize=True)
            else:
                bordered.save(output_path)

            logger.info(
                "Added border: %s -> %s",
                image_path.name,
                output_path.name,
            )
            return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed adding border to %s: %s", image_path, exc)
        return False


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description="Add decorative borders or polaroid frames to images."
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
        "-w",
        "--width",
        type=int,
        default=20,
        help="Border width in pixels (default: 20).",
    )
    parser.add_argument(
        "-c",
        "--color",
        type=str,
        default="#FFFFFF",
        help="Border hex color (default: '#FFFFFF').",
    )
    parser.add_argument(
        "--polaroid",
        action="store_true",
        help="Apply vintage polaroid matting frame with wide bottom border.",
    )
    parser.add_argument(
        "--bottom-margin",
        type=int,
        default=60,
        help="Additional bottom border margin for polaroid frame (default: 60).",
    )
    parser.add_argument(
        "--suffix",
        type=str,
        default="_border",
        help="Filename suffix for output files (default: '_border').",
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

    border_rgb = parse_hex_color(parsed_args.color)
    success_cnt = 0

    for src in image_files:
        rel = src.relative_to(input_path) if input_path.is_dir() else Path(src.name)
        dst = out_dir / rel.parent / f"{rel.stem}{parsed_args.suffix}{rel.suffix}"

        ok = add_image_border(
            src,
            dst,
            border_width=parsed_args.width,
            border_color=border_rgb,
            polaroid=parsed_args.polaroid,
            bottom_margin=parsed_args.bottom_margin,
            quality=parsed_args.quality,
        )
        if ok:
            success_cnt += 1

    logger.info(
        "Successfully added borders to %d/%d images.",
        success_cnt,
        len(image_files),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
