"""Convert images to base64 Data URIs / strings or decode base64 back to image files.

This module encodes local image files into base64 Data URIs suitable for embedding
directly into HTML/CSS files, and decodes raw base64 data back to binary image files.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments

import argparse
import base64
import logging
import mimetypes
import sys
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


def encode_image_to_base64(
    image_path: Path,
    data_uri: bool = True,
) -> Optional[str]:
    """Encode an image file to a base64 string or Data URI.

    Args:
        image_path: Path to input image file.
        data_uri: If True, prefixes base64 string with 'data:image/...;base64,'.

    Returns:
        Base64 string or Data URI, or None if encoding fails.
    """
    if not image_path.exists() or not image_path.is_file():
        logger.error("Image file does not exist: %s", image_path)
        return None

    try:
        raw_bytes = image_path.read_bytes()
        encoded = base64.b64encode(raw_bytes).decode("utf-8")

        if data_uri:
            mime_type, _ = mimetypes.guess_type(image_path)
            if not mime_type:
                ext = image_path.suffix.lower().lstrip(".")
                mime_type = f"image/{ext if ext != 'jpg' else 'jpeg'}"
            return f"data:{mime_type};base64,{encoded}"

        return encoded
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed encoding image %s to base64: %s", image_path, exc)
        return None


def decode_base64_to_image(
    base64_data: str,
    output_path: Path,
) -> bool:
    """Decode a base64 string or Data URI to an image file.

    Args:
        base64_data: Raw base64 string or 'data:image/...;base64,...' Data URI.
        output_path: Path to write decoded image file.

    Returns:
        True if decoding and file save succeeded, False otherwise.
    """
    try:
        cleaned_data = base64_data.strip()
        if "," in cleaned_data and cleaned_data.startswith("data:"):
            cleaned_data = cleaned_data.split(",", 1)[1]

        raw_bytes = base64.b64decode(cleaned_data)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(raw_bytes)

        logger.info("Decoded base64 to image file: %s", output_path.name)
        return True
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed decoding base64 data to %s: %s", output_path, exc)
        return False


def setup_cli_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser.

    Returns:
        Configured ArgumentParser object.
    """
    parser = argparse.ArgumentParser(
        description="Encode images to base64 or decode base64 strings to images."
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    # Encode subcommand
    encode_parser = subparsers.add_parser(
        "encode",
        help="Encode image file to base64 string.",
    )
    encode_parser.add_argument("input", type=str, help="Input image file path.")
    encode_parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Optional output text file path to save base64 string.",
    )
    encode_parser.add_argument(
        "--raw",
        action="store_true",
        help="Output raw base64 string without 'data:image/...' prefix.",
    )

    # Decode subcommand
    decode_parser = subparsers.add_parser(
        "decode",
        help="Decode base64 string to image file.",
    )
    decode_parser.add_argument(
        "input",
        type=str,
        help="Input text file containing base64 data or raw base64 string.",
    )
    decode_parser.add_argument(
        "-o",
        "--output",
        type=str,
        required=True,
        help="Target output image file path (e.g. 'output.png').",
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

    if parsed_args.mode == "encode":
        in_path = Path(parsed_args.input)
        b64_result = encode_image_to_base64(in_path, data_uri=not parsed_args.raw)
        if b64_result is None:
            return 1

        if parsed_args.output:
            out_file = Path(parsed_args.output)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(b64_result, encoding="utf-8")
            logger.info("Saved base64 output to %s", out_file)
        else:
            print(b64_result)
        return 0

    if parsed_args.mode == "decode":
        in_param = parsed_args.input
        in_file = Path(in_param)
        if in_file.exists() and in_file.is_file():
            b64_str = in_file.read_text(encoding="utf-8").strip()
        else:
            b64_str = in_param

        out_path = Path(parsed_args.output)
        ok = decode_base64_to_image(b64_str, out_path)
        return 0 if ok else 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
