"""Dim image backgrounds with customizable dark overlays for text legibility.

This module applies semi-transparent dark tint overlays or vignette gradients to photos,
enhancing contrast so overlaid text captions or graphics stand out clearly.
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
    from PIL import Image, ImageEnhance

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}

TupleRGB = Tuple[int, int, int]


def dim_image_background(
    image_path: Path,
    output_path: Path,
    dim_factor: float = 0.5,
    overlay_color: TupleRGB = (0, 0, 0),
    opacity: float = 0.4,
    quality: int = 90,
) -> bool:
    """Dim image background using brightness reduction and translucent tint.

    Args:
        image_path: Source image file path.
        output_path: Output image file path.
        dim_factor: Brightness multiplier (0.0 to 1.0, default: 0.5).
        overlay_color: RGB tint overlay color (default: black).
        opacity: Overlay opacity fraction (0.0 to 1.0, default: 0.4).
        quality: JPEG/WebP quality rating (1-100).

    Returns:
        True if dimming succeeded, False otherwise.
    """
    if not HAS_PIL:
        logger.error("Pillow package is required.")
        return False

    try:
        with Image.open(image_path) as img:
            base_img = img.convert("RGBA")

            # 1. Reduce overall image brightness
            if dim_factor != 1.0:
                enh = ImageEnhance.Brightness(base_img)  # type: ignore[no-untyped-call]
                base_img = enh.enhance(dim_factor)  # type: ignore[no-untyped-call]

            # 2. Composite semi-transparent overlay
            if opacity > 0.0:
                alpha_val = int(min(1.0, max(0.0, opacity)) * 255)
                overlay = Image.new(
                    "RGBA",
                    base_img.size,
                    overlay_color + (alpha_val,),
                )
                base_img = Image.alpha_composite(base_img, overlay)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            if output_path.suffix.lower() in (".jpg", ".jpeg"):
                final_rgb = base_img.convert("RGB")
                final_rgb.save(output_path, "JPEG", quality=quality, optimize=True)
            else:
                base_img.save(output_path)

            logger.info(
                "Dimmed background: %s -> %s",
                image_path.name,
                output_path.name,
            )
            return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed dimming background for %s: %s", image_path, exc)
        return False


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description="Dim image backgrounds for improved text legibility."
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
        "-d",
        "--dim",
        type=float,
        default=0.5,
        help="Brightness scale factor between 0.0 and 1.0 (default: 0.5).",
    )
    parser.add_argument(
        "-p",
        "--opacity",
        type=float,
        default=0.4,
        help="Dark overlay opacity between 0.0 and 1.0 (default: 0.4).",
    )
    parser.add_argument(
        "--suffix",
        type=str,
        default="_dimmed",
        help="Filename suffix for output files (default: '_dimmed').",
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
        rel = src.relative_to(input_path) if input_path.is_dir() else Path(src.name)
        dst = out_dir / rel.parent / f"{rel.stem}{parsed_args.suffix}{rel.suffix}"

        ok = dim_image_background(
            src,
            dst,
            dim_factor=parsed_args.dim,
            opacity=parsed_args.opacity,
            quality=parsed_args.quality,
        )
        if ok:
            success_cnt += 1

    logger.info(
        "Successfully dimmed background for %d/%d images.",
        success_cnt,
        len(image_files),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
