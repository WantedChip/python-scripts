"""Resize images in a directory with customizable dimensions.

This module provides batch image resizing utilities supporting pixel dimensions,
scaling factors, maximum bounding constraints, and resampling filters.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-return-statements

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


def calculate_target_dimensions(
    orig_width: int,
    orig_height: int,
    target_width: Optional[int] = None,
    target_height: Optional[int] = None,
    scale: Optional[float] = None,
    max_dim: Optional[int] = None,
    preserve_aspect: bool = True,
) -> Tuple[int, int]:
    """Calculate output width and height based on resizing constraints.

    Args:
        orig_width: Source image width in pixels.
        orig_height: Source image height in pixels.
        target_width: Specified target width in pixels.
        target_height: Specified target height in pixels.
        scale: Scaling percentage factor (e.g. 0.5 for 50%).
        max_dim: Maximum width or height constraint.
        preserve_aspect: Whether to keep original aspect ratio.

    Returns:
        Tuple of (new_width, new_height).
    """
    if orig_width <= 0 or orig_height <= 0:
        return 1, 1

    if scale is not None and scale > 0:
        return max(1, int(orig_width * scale)), max(1, int(orig_height * scale))

    if max_dim is not None and max_dim > 0:
        if orig_width >= orig_height:
            new_w = max_dim
            new_h = max(1, int(orig_height * (max_dim / orig_width)))
        else:
            new_h = max_dim
            new_w = max(1, int(orig_width * (max_dim / orig_height)))
        return new_w, new_h

    if target_width and not target_height:
        if preserve_aspect:
            ratio = target_width / orig_width
            return target_width, max(1, int(orig_height * ratio))
        return target_width, orig_height

    if target_height and not target_width:
        if preserve_aspect:
            ratio = target_height / orig_height
            return max(1, int(orig_width * ratio)), target_height
        return orig_width, target_height

    if target_width and target_height:
        if preserve_aspect:
            ratio = min(target_width / orig_width, target_height / orig_height)
            return max(1, int(orig_width * ratio)), max(1, int(orig_height * ratio))
        return target_width, target_height

    return orig_width, orig_height


def resize_image(
    image_path: Path,
    output_path: Path,
    target_width: Optional[int] = None,
    target_height: Optional[int] = None,
    scale: Optional[float] = None,
    max_dim: Optional[int] = None,
    preserve_aspect: bool = True,
    quality: int = 90,
    dry_run: bool = False,
) -> bool:
    """Resize a single image file and save to output path.

    Args:
        image_path: Path to input image file.
        output_path: Destination path for resized image.
        target_width: Specified target width.
        target_height: Specified target height.
        scale: Scaling multiplier.
        max_dim: Bounding dimension limit.
        preserve_aspect: Keep original aspect ratio flag.
        quality: JPEG/WebP compression quality (1-100).
        dry_run: Preview sizing without modifying disk.

    Returns:
        True if resizing succeeded or previewed, False otherwise.
    """
    if not HAS_PIL:
        logger.error("Pillow package is required for image processing.")
        return False

    try:
        with Image.open(image_path) as img:
            orig_w, orig_h = img.size
            new_w, new_h = calculate_target_dimensions(
                orig_w,
                orig_h,
                target_width=target_width,
                target_height=target_height,
                scale=scale,
                max_dim=max_dim,
                preserve_aspect=preserve_aspect,
            )

            logger.info(
                "%s: %dx%d -> %dx%d (%s)",
                image_path.name,
                orig_w,
                orig_h,
                new_w,
                new_h,
                output_path.name,
            )

            if dry_run:
                return True

            output_path.parent.mkdir(parents=True, exist_ok=True)
            resample_filter = getattr(Image, "Resampling", Image).LANCZOS
            resized_img = img.resize((new_w, new_h), resample_filter)

            if output_path.suffix.lower() in (".jpg", ".jpeg"):
                if resized_img.mode in ("RGBA", "P"):
                    resized_img = resized_img.convert("RGB")
                resized_img.save(output_path, quality=quality, optimize=True)
            else:
                resized_img.save(output_path)
            return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed to process %s: %s", image_path, exc)
        return False


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct argument parser for CLI interface.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        description="Batch resize images in a folder with aspect ratio options."
    )
    parser.add_argument(
        "input",
        type=str,
        help="Input image file path or directory path.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Output directory path. Defaults to input directory.",
    )
    parser.add_argument(
        "-w",
        "--width",
        type=int,
        help="Target image width in pixels.",
    )
    parser.add_argument(
        "-H",
        "--height",
        type=int,
        help="Target image height in pixels.",
    )
    parser.add_argument(
        "-s",
        "--scale",
        type=float,
        help="Scale factor multiplier (e.g. 0.5 for 50%% size).",
    )
    parser.add_argument(
        "-m",
        "--max-dim",
        type=int,
        help="Maximum width/height bounding dimension.",
    )
    parser.add_argument(
        "--no-aspect",
        action="store_true",
        help="Do not preserve original aspect ratio (stretch to fit).",
    )
    parser.add_argument(
        "-q",
        "--quality",
        type=int,
        default=90,
        help="Image output quality 1-100 (default: 90).",
    )
    parser.add_argument(
        "--suffix",
        type=str,
        default="",
        help="Filename suffix for output files (e.g. '_resized').",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview resize operations without saving files.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable detailed verbose logging.",
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
        if input_path.suffix.lower() in SUPPORTED_EXTENSIONS:
            image_files.append(input_path)
    elif input_path.is_dir():
        for root, _, files in os.walk(input_path):
            for file_name in files:
                p = Path(root) / file_name
                if p.suffix.lower() in SUPPORTED_EXTENSIONS:
                    image_files.append(p)

    if not image_files:
        logger.warning("No supported image files found in input path.")
        return 0

    out_dir = Path(parsed_args.output) if parsed_args.output else input_path.parent
    if input_path.is_dir() and not parsed_args.output:
        out_dir = input_path

    success_count = 0
    preserve_aspect = not parsed_args.no_aspect

    for img_file in image_files:
        rel_path = (
            img_file.relative_to(input_path)
            if input_path.is_dir()
            else Path(img_file.name)
        )
        stem = rel_path.stem + parsed_args.suffix
        out_file = out_dir / rel_path.parent / f"{stem}{rel_path.suffix}"

        ok = resize_image(
            img_file,
            out_file,
            target_width=parsed_args.width,
            target_height=parsed_args.height,
            scale=parsed_args.scale,
            max_dim=parsed_args.max_dim,
            preserve_aspect=preserve_aspect,
            quality=parsed_args.quality,
            dry_run=parsed_args.dry_run,
        )
        if ok:
            success_count += 1

    logger.info(
        "Completed processing %d/%d images successfully.",
        success_count,
        len(image_files),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
