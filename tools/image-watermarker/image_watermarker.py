"""Add text or image watermarks to all photos in a directory.

This module provides batch image watermarking capabilities with customizable
text, font size, opacity, logo placement, margin, and tiling modes.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any, List, Optional, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}


def calculate_watermark_position(
    bg_size: Tuple[int, int],
    wm_size: Tuple[int, int],
    position: str = "bottom-right",
    margin: int = 20,
) -> Tuple[int, int]:
    """Calculate (x, y) placement coordinates for a watermark.

    Args:
        bg_size: Tuple of (bg_width, bg_height).
        wm_size: Tuple of (wm_width, wm_height).
        position: Alignment preset ('top-left', 'top-right', 'center', etc.).
        margin: Edge margin offset in pixels.

    Returns:
        Tuple of (x, y) offset integers.
    """
    bg_w, bg_h = bg_size
    wm_w, wm_h = wm_size

    pos_map = {
        "top-left": (margin, margin),
        "top-right": (max(0, bg_w - wm_w - margin), margin),
        "bottom-left": (margin, max(0, bg_h - wm_h - margin)),
        "bottom-right": (
            max(0, bg_w - wm_w - margin),
            max(0, bg_h - wm_h - margin),
        ),
        "center": (max(0, (bg_w - wm_w) // 2), max(0, (bg_h - wm_h) // 2)),
    }
    return pos_map.get(position.lower(), pos_map["bottom-right"])


def apply_watermark(
    image_path: Path,
    output_path: Path,
    text: Optional[str] = None,
    watermark_img_path: Optional[Path] = None,
    position: str = "bottom-right",
    opacity: float = 0.5,
    margin: int = 20,
    font_size: int = 36,
) -> bool:
    """Apply text or image watermark to a target photo.

    Args:
        image_path: Source image file path.
        output_path: Destination output file path.
        text: Text string to watermark.
        watermark_img_path: Path to logo image watermark.
        position: Placement preset ('bottom-right', 'center', 'tile', etc.).
        opacity: Opacity float from 0.0 to 1.0.
        margin: Padding margin in pixels.
        font_size: Point size for text watermark.

    Returns:
        True if watermarked successfully, False otherwise.
    """
    if not HAS_PIL:
        logger.error("Pillow package is required.")
        return False

    try:
        with Image.open(image_path) as base_img:
            base_rgba = base_img.convert("RGBA")
            overlay = Image.new("RGBA", base_rgba.size, (255, 255, 255, 0))

            alpha_int = max(0, min(255, int(opacity * 255)))

            if watermark_img_path and watermark_img_path.exists():
                with Image.open(watermark_img_path) as wm:
                    wm_rgba = wm.convert("RGBA")
                    # Adjust opacity of logo image
                    wm_channels = list(wm_rgba.split())
                    wm_channels[3] = wm_channels[3].point(lambda p: int(p * opacity))
                    wm_rgba = Image.merge("RGBA", wm_channels)

                    if position == "tile":
                        for x in range(0, base_rgba.width, wm_rgba.width + margin):
                            for y in range(
                                0, base_rgba.height, wm_rgba.height + margin
                            ):
                                overlay.paste(wm_rgba, (x, y), wm_rgba)
                    else:
                        x, y = calculate_watermark_position(
                            base_rgba.size, wm_rgba.size, position, margin
                        )
                        overlay.paste(wm_rgba, (x, y), wm_rgba)
            elif text:
                draw = ImageDraw.Draw(overlay)
                # load_default() returns a different font class than
                # truetype() depending on the Pillow version, so widen the
                # declared type to cover both.
                font: Any
                try:
                    font = ImageFont.truetype("arial.ttf", font_size)
                except OSError:
                    font = ImageFont.load_default()

                bbox = draw.textbbox((0, 0), text, font=font)
                wm_w = int(bbox[2] - bbox[0])
                wm_h = int(bbox[3] - bbox[1])

                if position == "tile":
                    for x in range(0, base_rgba.width, wm_w + margin * 2):
                        for y in range(0, base_rgba.height, wm_h + margin * 2):
                            draw.text(
                                (x, y),
                                text,
                                fill=(255, 255, 255, alpha_int),
                                font=font,
                            )
                else:
                    x, y = calculate_watermark_position(
                        base_rgba.size, (wm_w, wm_h), position, margin
                    )
                    draw.text((x, y), text, fill=(255, 255, 255, alpha_int), font=font)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            watermarked = Image.alpha_composite(base_rgba, overlay)

            if output_path.suffix.lower() in (".jpg", ".jpeg"):
                watermarked = watermarked.convert("RGB")
                watermarked.save(output_path, quality=90, optimize=True)
            else:
                watermarked.save(output_path)

            logger.info("Watermarked %s -> %s", image_path.name, output_path.name)
            return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed to watermark %s: %s", image_path, exc)
        return False


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description="Add text or image watermarks to all photos in a directory."
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
        help="Output directory path. Defaults to input directory.",
    )
    parser.add_argument(
        "-t",
        "--text",
        type=str,
        help="Text string to watermark.",
    )
    parser.add_argument(
        "-w",
        "--watermark-image",
        type=str,
        help="Path to logo/watermark image file.",
    )
    parser.add_argument(
        "-p",
        "--position",
        choices=[
            "top-left",
            "top-right",
            "bottom-left",
            "bottom-right",
            "center",
            "tile",
        ],
        default="bottom-right",
        help="Watermark alignment position (default: bottom-right).",
    )
    parser.add_argument(
        "--opacity",
        type=float,
        default=0.5,
        help="Watermark opacity from 0.0 to 1.0 (default: 0.5).",
    )
    parser.add_argument(
        "--margin",
        type=int,
        default=20,
        help="Edge margin in pixels (default: 20).",
    )
    parser.add_argument(
        "--font-size",
        type=int,
        default=36,
        help="Text font size in points (default: 36).",
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

    if not parsed_args.text and not parsed_args.watermark_image:
        logger.error("Must specify either --text or --watermark-image.")
        return 1

    input_path = Path(parsed_args.input)
    if not input_path.exists():
        logger.error("Input path does not exist: %s", input_path)
        return 1

    wm_img_path = (
        Path(parsed_args.watermark_image) if parsed_args.watermark_image else None
    )

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
        logger.warning("No supported image files found to watermark.")
        return 0

    out_dir = Path(parsed_args.output) if parsed_args.output else input_path.parent
    if input_path.is_dir() and not parsed_args.output:
        out_dir = input_path

    success_cnt = 0
    for src in image_files:
        rel = src.relative_to(input_path) if input_path.is_dir() else Path(src.name)
        dst = out_dir / rel.parent / f"{rel.stem}_wm{rel.suffix}"

        ok = apply_watermark(
            src,
            dst,
            text=parsed_args.text,
            watermark_img_path=wm_img_path,
            position=parsed_args.position,
            opacity=parsed_args.opacity,
            margin=parsed_args.margin,
            font_size=parsed_args.font_size,
        )
        if ok:
            success_cnt += 1

    logger.info(
        "Watermarked %d/%d images successfully.",
        success_cnt,
        len(image_files),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
