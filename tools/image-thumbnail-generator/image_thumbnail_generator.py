"""Generate thumbnail versions of images with maximum bounding dimensions.

This module creates thumbnail images maintaining original aspect ratios or
square padded bounding boxes with customizable maximum dimensions and suffixes.
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

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}


def generate_thumbnail(
    image_path: Path,
    output_path: Path,
    max_size: Tuple[int, int] = (256, 256),
    square: bool = False,
    bg_color: Tuple[int, int, int] = (255, 255, 255),
    quality: int = 85,
) -> bool:
    """Generate a thumbnail image file.

    Args:
        image_path: Source image file path.
        output_path: Output thumbnail file path.
        max_size: Maximum bounding box dimensions (width, height).
        square: If True, pads thumbnail into a square bounding canvas.
        bg_color: Background padding RGB color tuple for square mode.
        quality: JPEG/WebP quality rating (1-100).

    Returns:
        True if thumbnail created successfully, False otherwise.
    """
    if not HAS_PIL:
        logger.error("Pillow package is required.")
        return False

    try:
        with Image.open(image_path) as img:
            resample_filter = getattr(Image, "Resampling", Image).LANCZOS
            thumb_img = img.copy()
            thumb_img.thumbnail(max_size, resample_filter)

            if square:
                side = max(max_size)
                canvas_mode = "RGB" if img.mode == "RGB" else "RGBA"
                canvas = Image.new(canvas_mode, (side, side), bg_color)
                offset_x = (side - thumb_img.width) // 2
                offset_y = (side - thumb_img.height) // 2

                if thumb_img.mode in ("RGBA", "LA") or (
                    thumb_img.mode == "P" and "transparency" in thumb_img.info
                ):
                    mask_img = thumb_img.convert("RGBA")
                    canvas.paste(thumb_img, (offset_x, offset_y), mask_img)
                else:
                    canvas.paste(thumb_img, (offset_x, offset_y))
                final_img = canvas
            else:
                final_img = thumb_img

            output_path.parent.mkdir(parents=True, exist_ok=True)
            if output_path.suffix.lower() in (".jpg", ".jpeg"):
                if final_img.mode in ("RGBA", "P"):
                    final_img = final_img.convert("RGB")
                final_img.save(output_path, quality=quality, optimize=True)
            else:
                final_img.save(output_path)

            logger.info(
                "Generated thumbnail %s -> %s",
                image_path.name,
                output_path.name,
            )
            return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed generating thumbnail for %s: %s", image_path, exc)
        return False


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description="Generate thumbnail versions of images in bulk."
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
        "-s",
        "--size",
        type=int,
        default=256,
        help="Maximum thumbnail dimension in pixels (default: 256).",
    )
    parser.add_argument(
        "--square",
        action="store_true",
        help="Pad thumbnail into a square canvas matching max size.",
    )
    parser.add_argument(
        "--suffix",
        type=str,
        default="_thumb",
        help="Filename suffix for thumbnails (default: '_thumb').",
    )
    parser.add_argument(
        "-q",
        "--quality",
        type=int,
        default=85,
        help="Output image quality rating 1-100 (default: 85).",
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
        logger.warning("No supported image files found.")
        return 0

    out_dir = Path(parsed_args.output) if parsed_args.output else input_path.parent
    if input_path.is_dir() and not parsed_args.output:
        out_dir = input_path

    max_dim = (parsed_args.size, parsed_args.size)
    success_cnt = 0

    for src in image_files:
        rel = src.relative_to(input_path) if input_path.is_dir() else Path(src.name)
        dst = out_dir / rel.parent / f"{rel.stem}{parsed_args.suffix}{rel.suffix}"

        ok = generate_thumbnail(
            src,
            dst,
            max_size=max_dim,
            square=parsed_args.square,
            quality=parsed_args.quality,
        )
        if ok:
            success_cnt += 1

    logger.info(
        "Generated %d/%d thumbnails successfully.",
        success_cnt,
        len(image_files),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
