"""Crop images to a specified aspect ratio from the center, ideal for profile photos.

This module provides center-cropping utilities supporting target aspect ratios
('1:1', '16:9', '4:3', '4:5', '3:2', '9:16') or explicit width and height dimensions.
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

ASPECT_RATIO_PRESETS = {
    "1:1": (1, 1),
    "16:9": (16, 9),
    "4:3": (4, 3),
    "4:5": (4, 5),
    "3:2": (3, 2),
    "9:16": (9, 16),
}


def calculate_crop_box(
    orig_w: int,
    orig_h: int,
    aspect_w: float,
    aspect_h: float,
    focal_position: str = "center",
) -> Tuple[int, int, int, int]:
    """Calculate (left, top, right, bottom) bounding box for center cropping.

    Args:
        orig_w: Original image width.
        orig_h: Original image height.
        aspect_w: Target aspect ratio width ratio.
        aspect_h: Target aspect ratio height ratio.
        focal_position: Vertical focal bias ('top', 'center', 'bottom').

    Returns:
        Tuple of (left, top, right, bottom) box coordinates.
    """
    target_ratio = aspect_w / aspect_h
    orig_ratio = orig_w / orig_h

    if orig_ratio > target_ratio:
        # Image is wider than target ratio: crop sides
        crop_w = int(orig_h * target_ratio)
        crop_h = orig_h
    else:
        # Image is taller than target ratio: crop top/bottom
        crop_w = orig_w
        crop_h = int(orig_w / target_ratio)

    left = (orig_w - crop_w) // 2
    right = left + crop_w

    if focal_position == "top":
        top = 0
    elif focal_position == "bottom":
        top = orig_h - crop_h
    else:
        top = (orig_h - crop_h) // 2

    bottom = top + crop_h
    return left, top, right, bottom


def crop_image_center(
    input_file: Path,
    output_file: Path,
    aspect_ratio: str = "1:1",
    target_width: Optional[int] = None,
    target_height: Optional[int] = None,
    focal_position: str = "center",
    quality: int = 90,
) -> bool:
    """Crop an image file from the geometric center.

    Args:
        input_file: Path to source image file.
        output_file: Target output image file path.
        aspect_ratio: Target aspect ratio preset string (e.g. '1:1', '16:9').
        target_width: Optional target output width to resize after cropping.
        target_height: Optional target output height to resize after cropping.
        focal_position: Vertical focus bias ('top', 'center', 'bottom').
        quality: JPEG/WebP quality rating (1-100).

    Returns:
        True if image was cropped successfully, False otherwise.
    """
    if not HAS_PIL:
        logger.error("Pillow package is required.")
        return False

    try:
        if aspect_ratio in ASPECT_RATIO_PRESETS:
            preset_w, preset_h = ASPECT_RATIO_PRESETS[aspect_ratio]
            aw, ah = float(preset_w), float(preset_h)
        else:
            parts = aspect_ratio.split(":")
            if len(parts) == 2:
                aw, ah = float(parts[0]), float(parts[1])
            else:
                aw, ah = 1.0, 1.0

        with Image.open(input_file) as img:
            orig_w, orig_h = img.size
            box = calculate_crop_box(orig_w, orig_h, aw, ah, focal_position)
            cropped_img = img.crop(box)

            if target_width or target_height:
                resample_filter = getattr(Image, "Resampling", Image).LANCZOS
                tw = target_width or cropped_img.width
                th = target_height or cropped_img.height
                cropped_img = cropped_img.resize((tw, th), resample_filter)

            output_file.parent.mkdir(parents=True, exist_ok=True)
            if output_file.suffix.lower() in (".jpg", ".jpeg"):
                if cropped_img.mode in ("RGBA", "P"):
                    cropped_img = cropped_img.convert("RGB")
                cropped_img.save(output_file, "JPEG", quality=quality, optimize=True)
            else:
                cropped_img.save(output_file)

            logger.info("Cropped image: %s -> %s", input_file.name, output_file.name)
            return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed to crop %s: %s", input_file, exc)
        return False


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description="Crop images to a specified aspect ratio from the center."
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
        "-a",
        "--aspect-ratio",
        default="1:1",
        help=(
            "Target aspect ratio preset ('1:1', '16:9', '4:3', "
            "'4:5', '3:2', '9:16') or W:H."
        ),
    )
    parser.add_argument(
        "-w",
        "--width",
        type=int,
        help="Optional width to resize cropped output image in pixels.",
    )
    parser.add_argument(
        "-H",
        "--height",
        type=int,
        help="Optional height to resize cropped output image in pixels.",
    )
    parser.add_argument(
        "-f",
        "--focal-position",
        choices=["top", "center", "bottom"],
        default="center",
        help="Vertical alignment focal bias (default: center).",
    )
    parser.add_argument(
        "--suffix",
        type=str,
        default="_crop",
        help="Filename suffix for cropped output files (default: '_crop').",
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
        logger.warning("No supported image files found to crop.")
        return 0

    out_dir = Path(parsed_args.output) if parsed_args.output else input_path.parent
    if input_path.is_dir() and not parsed_args.output:
        out_dir = input_path

    success_cnt = 0
    for src in image_files:
        rel = src.relative_to(input_path) if input_path.is_dir() else Path(src.name)
        dst = out_dir / rel.parent / f"{rel.stem}{parsed_args.suffix}{rel.suffix}"

        ok = crop_image_center(
            src,
            dst,
            aspect_ratio=parsed_args.aspect_ratio,
            target_width=parsed_args.width,
            target_height=parsed_args.height,
            focal_position=parsed_args.focal_position,
            quality=parsed_args.quality,
        )
        if ok:
            success_cnt += 1

    logger.info(
        "Successfully center-cropped %d/%d images.",
        success_cnt,
        len(image_files),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
