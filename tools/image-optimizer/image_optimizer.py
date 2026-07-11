"""Image Optimization Pipeline.

Recursively resizes, compresses, and converts images while preserving originals
and applying metadata rules.
"""

import argparse
import fnmatch
import logging
import sys
from pathlib import Path
from typing import Optional, cast

from PIL import Image

# pylint: disable=import-error, duplicate-code


logger = logging.getLogger("image_optimizer")


def setup_logging(verbose: bool) -> None:
    """Configure logging level.

    Args:
        verbose: True for DEBUG, False for INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.setLevel(level)
    logger.addHandler(handler)
    # Configure root logger minimal settings so external libraries don't pollute
    logging.basicConfig(level=logging.WARNING, handlers=[handler])


def get_exif_bytes(img: Image.Image, rule: str) -> Optional[bytes]:
    """Retrieve EXIF bytes according to metadata preservation rules.

    Args:
        img: The Pillow Image object.
        rule: 'strip', 'keep', or 'orientation'.

    Returns:
        Exif bytes if found/requested, otherwise None.
    """
    if rule == "strip":
        return None

    try:
        if rule == "keep":
            return cast(Optional[bytes], img.info.get("exif"))

        if rule == "orientation":
            exif = img.getexif()
            if exif and 274 in exif:
                new_exif = Image.Exif()
                new_exif[274] = exif[274]
                val_bytes = new_exif.tobytes()
                if isinstance(val_bytes, bytes):
                    return val_bytes
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.warning("Failed to parse EXIF metadata: %s", err)

    return None


def resize_image(
    img: Image.Image,
    width: Optional[int],
    height: Optional[int],
    scale: Optional[float],
) -> Image.Image:
    """Resize an image based on dimensions or scale factor.

    Args:
        img: The Pillow Image object.
        width: Target width in pixels.
        height: Target height in pixels.
        scale: Scale percentage (e.g. 0.5 for 50%).

    Returns:
        The resized Pillow Image object.
    """
    orig_w, orig_h = img.size

    if scale is not None:
        target_w = int(orig_w * scale)
        target_h = int(orig_h * scale)
        logger.debug(
            "Resizing by scale factor %.2f: (%d, %d) -> (%d, %d)",
            scale,
            orig_w,
            orig_h,
            target_w,
            target_h,
        )
        return img.resize((target_w, target_h), Image.Resampling.LANCZOS)

    if width is not None or height is not None:
        if width is not None and height is not None:
            # Exact dimensions
            logger.debug("Resizing to exact dimensions: (%d, %d)", width, height)
            return img.resize((width, height), Image.Resampling.LANCZOS)

        # Aspect ratio preserving
        if width is not None:
            ratio = width / orig_w
            target_h = int(orig_h * ratio)
            logger.debug(
                "Resizing width to %d: height auto-calculated to %d", width, target_h
            )
            return img.resize((width, target_h), Image.Resampling.LANCZOS)

        if height is not None:
            ratio = height / orig_h
            target_w = int(orig_w * ratio)
            logger.debug(
                "Resizing height to %d: width auto-calculated to %d", height, target_w
            )
            return img.resize((target_w, height), Image.Resampling.LANCZOS)

    return img


def process_image(
    src_path: Path,
    dest_path: Path,
    args: argparse.Namespace,
) -> bool:
    """Process a single image: resize, compress, convert, and save.

    Args:
        src_path: Path to the source image.
        dest_path: Path to the output image destination.
        args: Parsed command-line arguments namespace.

    Returns:
        True if processed successfully, False otherwise.
    """
    try:
        with Image.open(src_path) as img:
            # 1. Resize
            resized = resize_image(img, args.width, args.height, args.scale)

            # 2. Get metadata bytes according to rule
            exif_bytes = get_exif_bytes(img, args.metadata)

            # 3. Determine save format and options
            fmt = dest_path.suffix.lstrip(".").upper()
            if fmt == "JPG":
                fmt = "JPEG"

            save_args = {}
            if fmt in ["JPEG", "WEBP"]:
                save_args["quality"] = args.quality
            elif fmt == "PNG":
                # convert png compression option (0-9) to pillow default (0-9)
                save_args["compress_level"] = args.png_optimize

            if exif_bytes:
                save_args["exif"] = exif_bytes

            # WebP/JPEG cannot be saved in RGBA/P mode to JPEG directly
            # without conversion.
            if fmt == "JPEG" and resized.mode in ("RGBA", "LA", "P"):

                logger.debug(
                    "Converting image mode %s to RGB for JPEG compatibility",
                    resized.mode,
                )
                resized = resized.convert("RGB")

            if args.dry_run:
                logger.info(
                    "[Dry Run] Would process and save: %s -> %s",
                    src_path.as_posix(),
                    dest_path.as_posix(),
                )
            else:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                resized.save(dest_path, format=fmt, **save_args)
                logger.debug("Saved processed image to: %s", dest_path.as_posix())

        return True
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.error("Failed to process image %s: %s", src_path.name, err)
        return False


def is_matching(name: str, include: str, exclude: str) -> bool:
    """Check if file matches include/exclude glob patterns.

    Args:
        name: Name of the file.
        include: Include glob pattern.
        exclude: Exclude glob pattern.

    Returns:
        True if matches include and does not match exclude.
    """
    if include and not fnmatch.fnmatch(name, include):
        return False
    if exclude and fnmatch.fnmatch(name, exclude):
        return False
    return True


def run_pipeline(args: argparse.Namespace) -> None:
    """Walk directories recursively and run the optimization pipeline.

    Args:
        args: Parsed command-line arguments namespace.
    """
    # pylint: disable=too-many-locals, too-many-branches, too-many-statements
    src_dir = Path(args.input)

    if not src_dir.exists():
        raise FileNotFoundError(f"Input directory does not exist: {src_dir}")

    # Determine out directory
    if args.output_dir:
        out_dir = Path(args.output_dir)
    else:
        out_dir = src_dir

    supported_suffixes = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}

    # Find files
    img_files = []
    if src_dir.is_file():
        if src_dir.suffix.lower() in supported_suffixes:
            img_files.append(src_dir)
    else:
        # Recursive glob search
        for path in src_dir.rglob("*"):
            if path.is_file() and path.suffix.lower() in supported_suffixes:
                img_files.append(path)

    if not img_files:
        logger.info("No supported images found to process.")
        return

    total_files = len(img_files)
    logger.info("Found %d images to process.", total_files)

    processed_count = 0
    total_orig_size = 0
    total_dest_size = 0

    for src_path in img_files:
        if not is_matching(src_path.name, args.include, args.exclude):
            logger.debug("Skipping file due to filters: %s", src_path.name)
            continue

        orig_size = src_path.stat().st_size
        if args.min_size and orig_size < args.min_size:
            logger.debug("Skipping file (too small): %s", src_path.name)
            continue
        if args.max_size and orig_size > args.max_size:
            logger.debug("Skipping file (too large): %s", src_path.name)
            continue

        # Compute output path
        if src_dir.is_file():
            rel_path = Path(src_path.name)
        else:
            rel_path = src_path.relative_to(src_dir)

        # Apply format conversion to suffix
        suffix = f".{args.format.lower()}" if args.format else src_path.suffix
        stem = rel_path.stem
        if args.suffix and not args.in_place:
            stem = f"{stem}{args.suffix}"

        dest_path = out_dir / rel_path.parent / f"{stem}{suffix}"

        # Prevent accidental overwrite unless explicitly requested
        if dest_path == src_path and not args.in_place:
            logger.warning(
                "Skipping %s to prevent overwriting original. "
                "Use --in-place or specify --output-dir/--suffix.",
                src_path.name,
            )
            continue

        logger.info("Processing: %s", src_path.as_posix())
        success = process_image(src_path, dest_path, args)

        if success:
            processed_count += 1
            total_orig_size += orig_size
            if not args.dry_run and dest_path.exists():
                total_dest_size += dest_path.stat().st_size
            else:
                total_dest_size += orig_size  # fallback metric estimate for dry-run

    if processed_count > 0:
        savings = total_orig_size - total_dest_size
        percent = (savings / total_orig_size * 100) if total_orig_size > 0 else 0
        logger.info("--- Optimization Summary ---")
        logger.info("Processed: %d/%d files", processed_count, total_files)
        logger.info("Original Size: %d bytes", total_orig_size)
        logger.info("Optimized Size: %d bytes", total_dest_size)
        logger.info("Wasted space reclaimed: %d bytes (%.2f%%)", savings, percent)
    else:
        logger.info("No images were optimized.")


def main() -> None:
    """CLI execution entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Image Optimization Pipeline — recursively resize, compress, "
            "and convert images."
        )
    )

    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Input file or directory containing images.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        help="Output directory. Preserves tree structure if outputting recursively.",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite original files (ignores --suffix).",
    )
    parser.add_argument(
        "--suffix",
        default="",
        help="Suffix to add to optimized filenames (e.g. '_opt').",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose debug logging."
    )

    # Transform Options
    parser.add_argument("--width", type=int, help="Target resize width in pixels.")
    parser.add_argument("--height", type=int, help="Target resize height in pixels.")
    parser.add_argument(
        "--scale",
        type=float,
        help="Scale factor (e.g. 0.5 for 50%). Width/height ignored if set.",
    )

    # Format / Compression Options
    parser.add_argument(
        "-f",
        "--format",
        choices=["JPEG", "PNG", "WEBP", "BMP", "TIFF"],
        help="Convert format.",
    )
    parser.add_argument(
        "-q",
        "--quality",
        type=int,
        default=85,
        help="JPEG/WebP compression quality (0-100).",
    )
    parser.add_argument(
        "--png-optimize",
        type=int,
        default=6,
        choices=range(0, 10),
        help="PNG optimization level (0-9).",
    )

    # Metadata Options
    parser.add_argument(
        "--metadata",
        choices=["strip", "keep", "orientation"],
        default="strip",
        help="EXIF metadata retention rule: strip, keep, or orientation only.",
    )

    # Filters
    parser.add_argument(
        "--include",
        default="",
        help="Include files matching glob pattern (e.g. '*.png').",
    )
    parser.add_argument(
        "--exclude",
        default="",
        help="Exclude files matching glob pattern (e.g. '*_opt.png').",
    )
    parser.add_argument(
        "--min-size",
        type=int,
        help="Process only files larger than this size in bytes.",
    )
    parser.add_argument(
        "--max-size",
        type=int,
        help="Process only files smaller than this size in bytes.",
    )

    # Dry-run
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only. Do not perform modifications.",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    try:
        run_pipeline(args)
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.error("Error: %s", err)
        sys.exit(1)


if __name__ == "__main__":
    main()
