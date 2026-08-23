"""Find visually similar or exact duplicate images using perceptual hashing.

This module computes difference hashes (dHash) for images and detects matching or
near-duplicate photo groups using Hamming distance similarity thresholds.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

try:
    from PIL import Image

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}


def compute_dhash(image_path: Path, hash_size: int = 8) -> Optional[int]:
    """Calculate difference hash (dHash) integer for an image.

    Args:
        image_path: Path to source image file.
        hash_size: Hash grid dimension size (default: 8 for 64-bit hash).

    Returns:
        Integer representing bit hash, or None if image fails to load.
    """
    if not HAS_PIL:
        logger.error("Pillow package is required.")
        return None

    try:
        with Image.open(image_path) as img:
            # Resize image to (hash_size + 1, hash_size) in grayscale
            resized = img.convert("L").resize(
                (hash_size + 1, hash_size),
                getattr(Image, "Resampling", Image).LANCZOS,
            )
            pixels = list(resized.getdata())

            # Compute difference hash bits: adjacent horizontal pixel comparison
            diff = []
            for row in range(hash_size):
                for col in range(hash_size):
                    idx = row * (hash_size + 1) + col
                    diff.append(pixels[idx] > pixels[idx + 1])

            # Convert boolean array to integer hash
            decimal_val = 0
            for bit in diff:
                decimal_val = (decimal_val << 1) | int(bit)

            return decimal_val
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed calculating dHash for %s: %s", image_path, exc)
        return None


def hamming_distance(hash1: int, hash2: int) -> int:
    """Compute Hamming distance between two integer hashes.

    Args:
        hash1: First integer hash value.
        hash2: Second integer hash value.

    Returns:
        Number of differing bits.
    """
    return bin(hash1 ^ hash2).count("1")


def find_duplicates(
    image_dir: Path,
    threshold: int = 4,
) -> List[List[Dict[str, str]]]:
    """Find groups of duplicate or visually similar images.

    Args:
        image_dir: Directory containing images to scan.
        threshold: Max Hamming distance threshold for similarity (0 = identical).

    Returns:
        List of duplicate groups, each containing dicts with file path and hash.
    """
    if not image_dir.exists() or not image_dir.is_dir():
        logger.error("Directory does not exist: %s", image_dir)
        return []

    hashes: Dict[Path, int] = {}
    for root, _, files in os.walk(image_dir):
        for fname in files:
            fp = Path(root) / fname
            if fp.suffix.lower() in SUPPORTED_EXTENSIONS:
                h = compute_dhash(fp)
                if h is not None:
                    hashes[fp] = h

    paths = list(hashes.keys())
    visited: Set[Path] = set()
    groups: List[List[Dict[str, str]]] = []

    for i, p1 in enumerate(paths):
        if p1 in visited:
            continue

        h1 = hashes[p1]
        current_group = [{"path": str(p1), "hash": hex(h1)}]

        for j in range(i + 1, len(paths)):
            p2 = paths[j]
            if p2 in visited:
                continue

            h2 = hashes[p2]
            dist = hamming_distance(h1, h2)
            if dist <= threshold:
                current_group.append({"path": str(p2), "hash": hex(h2)})
                visited.add(p2)

        if len(current_group) > 1:
            visited.add(p1)
            groups.append(current_group)

    return groups


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description="Find visually similar or exact duplicate images."
    )
    parser.add_argument(
        "directory",
        type=str,
        help="Target directory path containing images to scan.",
    )
    parser.add_argument(
        "-t",
        "--threshold",
        type=int,
        default=4,
        help="Max Hamming distance similarity threshold (default: 4, 0=exact).",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output display format (default: table).",
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

    target_dir = Path(parsed_args.directory)
    duplicate_groups = find_duplicates(target_dir, threshold=parsed_args.threshold)

    if parsed_args.format == "json":
        print(json.dumps(duplicate_groups, indent=2))
    else:
        if not duplicate_groups:
            print("No duplicate or similar images found.")
        else:
            print(f"=== Found {len(duplicate_groups)} Duplicate Image Groups ===")
            for idx, group in enumerate(duplicate_groups, start=1):
                print(f"\nGroup #{idx} ({len(group)} images):")
                for item in group:
                    print(f"  - {item['path']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
