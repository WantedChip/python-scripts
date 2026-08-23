"""Combine multiple images into a structured collage grid layout.

This module arranges multiple input photos into customizable NxM photo collage
grids with configurable spacing, cell padding, and background color.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import logging
import math
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
    """Parse hex string to RGB tuple.

    Args:
        hex_str: Hex color string (e.g. '#FFFFFF' or 'black').

    Returns:
        RGB tuple of integers.
    """
    cleaned = hex_str.lstrip("#").lower()
    if cleaned == "black":
        return (0, 0, 0)
    if cleaned == "white" or len(cleaned) != 6:
        return (255, 255, 255)
    try:
        r = int(cleaned[0:2], 16)
        g = int(cleaned[2:4], 16)
        b = int(cleaned[4:6], 16)
        return (r, g, b)
    except ValueError:
        return (255, 255, 255)


def create_collage(
    image_paths: List[Path],
    output_path: Path,
    cols: Optional[int] = None,
    cell_size: Tuple[int, int] = (300, 300),
    spacing: int = 10,
    bg_color: TupleRGB = (255, 255, 255),
) -> bool:
    """Assemble a list of images into a collage grid image.

    Args:
        image_paths: List of source image file paths.
        output_path: Path to write assembled collage.
        cols: Number of columns (auto-calculated if None).
        cell_size: Target (width, height) of individual cell slots.
        spacing: Grid cell margin/spacing in pixels.
        bg_color: Background canvas color RGB tuple.

    Returns:
        True if collage created successfully, False otherwise.
    """
    if not HAS_PIL:
        logger.error("Pillow package is required.")
        return False

    if not image_paths:
        logger.error("No input images provided for collage.")
        return False

    num_images = len(image_paths)
    if cols is None or cols <= 0:
        cols = int(math.ceil(math.sqrt(num_images)))

    rows = int(math.ceil(num_images / cols))
    cell_w, cell_h = cell_size

    canvas_w = (cols * cell_w) + ((cols + 1) * spacing)
    canvas_h = (rows * cell_h) + ((rows + 1) * spacing)

    try:
        canvas = Image.new("RGB", (canvas_w, canvas_h), bg_color)
        resample_filter = getattr(Image, "Resampling", Image).LANCZOS

        for idx, img_path in enumerate(image_paths):
            r = idx // cols
            c = idx % cols

            x = spacing + c * (cell_w + spacing)
            y = spacing + r * (cell_h + spacing)

            with Image.open(img_path) as img:
                cropped = ImageOps.fit(img, cell_size, resample_filter)
                if cropped.mode != "RGB":
                    cropped = cropped.convert("RGB")
                canvas.paste(cropped, (x, y))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.suffix.lower() in (".jpg", ".jpeg"):
            canvas.save(output_path, "JPEG", quality=90, optimize=True)
        else:
            canvas.save(output_path)

        logger.info(
            "Created collage with %d images -> %s",
            num_images,
            output_path.name,
        )
        return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed creating collage: %s", exc)
        return False


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description="Combine multiple images into a collage grid layout."
    )
    parser.add_argument(
        "input",
        type=str,
        help="Input image directory path or list of image files.",
        nargs="+",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        required=True,
        help="Output collage image file path (e.g. 'collage.jpg').",
    )
    parser.add_argument(
        "-c",
        "--cols",
        type=int,
        help="Number of columns in collage grid (auto-calculated if omitted).",
    )
    parser.add_argument(
        "--cell-width",
        type=int,
        default=300,
        help="Width of each grid cell slot in pixels (default: 300).",
    )
    parser.add_argument(
        "--cell-height",
        type=int,
        default=300,
        help="Height of each grid cell slot in pixels (default: 300).",
    )
    parser.add_argument(
        "-s",
        "--spacing",
        type=int,
        default=10,
        help="Grid spacing/margin between images in pixels (default: 10).",
    )
    parser.add_argument(
        "--bg-color",
        type=str,
        default="#FFFFFF",
        help="Canvas background hex color (default: '#FFFFFF').",
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

    image_paths: List[Path] = []
    for item in parsed_args.input:
        p = Path(item)
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
            image_paths.append(p)
        elif p.is_dir():
            for root, _, filenames in os.walk(p):
                for fname in filenames:
                    fp = Path(root) / fname
                    if fp.suffix.lower() in SUPPORTED_EXTENSIONS:
                        image_paths.append(fp)

    if not image_paths:
        logger.error("No valid image files found in specified inputs.")
        return 1

    bg_rgb = parse_hex_color(parsed_args.bg_color)
    output_path = Path(parsed_args.output)

    cell_size = (parsed_args.cell_width, parsed_args.cell_height)

    ok = create_collage(
        image_paths,
        output_path,
        cols=parsed_args.cols,
        cell_size=cell_size,
        spacing=parsed_args.spacing,
        bg_color=bg_rgb,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
