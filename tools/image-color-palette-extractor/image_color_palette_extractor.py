"""Extract dominant color palette from an image with hex codes and distributions.

This module computes top dominant color palettes using color quantization,
formatting hex codes, RGB values, percentage distribution, and ANSI color previews.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from PIL import Image

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

logger = logging.getLogger(__name__)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert RGB integers to hex color string.

    Args:
        r: Red component (0-255).
        g: Green component (0-255).
        b: Blue component (0-255).

    Returns:
        Hex formatted string like '#FF5733'.
    """
    return f"#{r:02x}{g:02x}{b:02x}".upper()


def extract_color_palette(
    image_path: Path,
    num_colors: int = 5,
    ignore_bg: bool = False,
) -> List[Dict[str, Any]]:
    """Extract top dominant colors from an image.

    Args:
        image_path: Path to source image file.
        num_colors: Number of dominant colors to extract.
        ignore_bg: Skip pure white or transparent background pixels.

    Returns:
        List of color metadata dicts containing hex, rgb, percentage, count.
    """
    if not HAS_PIL:
        logger.error("Pillow package is required.")
        return []

    try:
        with Image.open(image_path) as img:
            # Resize image down to speed up quantization while preserving palette
            img_small = img.copy()
            img_small.thumbnail((150, 150))

            if img_small.mode not in ("RGB", "RGBA"):
                img_small = img_small.convert("RGB")

            # Quantize image to extract dominant palette
            quantized = img_small.quantize(colors=num_colors + (2 if ignore_bg else 0))
            palette = quantized.getpalette()

            if not palette:
                return []

            color_counts = quantized.getcolors()
            if not color_counts:
                return []

            total_pixels = sum(c[0] for c in color_counts)
            # Sort by frequency descending
            color_counts.sort(key=lambda x: x[0], reverse=True)

            results: List[Dict[str, Any]] = []

            for count, ink in color_counts:
                # For quantized (P-mode) images the "ink" is the palette
                # index; stubs type getcolors()' second element as a generic
                # pixel-value union, so coerce explicitly.
                idx = int(ink)  # type: ignore[arg-type]
                r = palette[idx * 3]
                g = palette[idx * 3 + 1]
                b = palette[idx * 3 + 2]

                if ignore_bg and (r > 240 and g > 240 and b > 240):
                    continue

                pct = round((count / total_pixels) * 100, 2)
                hex_code = rgb_to_hex(r, g, b)

                results.append(
                    {
                        "hex": hex_code,
                        "rgb": [r, g, b],
                        "percentage": pct,
                        "count": count,
                    }
                )

                if len(results) >= num_colors:
                    break

            return results
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed to extract color palette from %s: %s", image_path, exc)
        return []


def format_ansi_swatch(r: int, g: int, b: int) -> str:
    """Format an ANSI truecolor swatch string for terminal display.

    Args:
        r: Red 0-255.
        g: Green 0-255.
        b: Blue 0-255.

    Returns:
        ANSI escape sequence block swatch string.
    """
    return f"\033[48;2;{r};{g};{b}m    \033[0m"


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description="Extract dominant color palette from an image."
    )
    parser.add_argument(
        "image",
        type=str,
        help="Path to source image file.",
    )
    parser.add_argument(
        "-n",
        "--num-colors",
        type=int,
        default=5,
        help="Number of dominant colors to extract (default: 5).",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["table", "json", "csv"],
        default="table",
        help="Output display format (default: table).",
    )
    parser.add_argument(
        "--ignore-bg",
        action="store_true",
        help="Ignore near-white background colors in calculation.",
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

    img_path = Path(parsed_args.image)
    if not img_path.exists():
        logger.error("Image file does not exist: %s", img_path)
        return 1

    palette_data = extract_color_palette(
        img_path,
        num_colors=parsed_args.num_colors,
        ignore_bg=parsed_args.ignore_bg,
    )

    if not palette_data:
        logger.error("Could not extract palette from %s.", img_path)
        return 1

    if parsed_args.format == "json":
        print(json.dumps(palette_data, indent=2))
    elif parsed_args.format == "csv":
        print("HEX,RGB,PERCENTAGE")
        for item in palette_data:
            rgb_str = f"\"{item['rgb'][0]},{item['rgb'][1]},{item['rgb'][2]}\""
            print(f"{item['hex']},{rgb_str},{item['percentage']}%")
    else:
        print(f"=== Dominant Color Palette: {img_path.name} ===")
        for item in palette_data:
            r, g, b = item["rgb"]
            swatch = format_ansi_swatch(r, g, b)
            print(
                f"{swatch} {item['hex']}  RGB({r:>3}, {g:>3}, {b:>3})  "
                f"{item['percentage']:>6.2f}%"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
