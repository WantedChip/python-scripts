"""Text Encoding Converter Utility.

Detects character encoding (UTF-8, Latin-1, Windows-1252, UTF-16, ASCII, etc.)
of text files using BOM and byte sequence analysis, and converts them to
a target encoding cleanly. Supports single file and bulk folder conversions.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-return-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union


def detect_encoding(data: bytes) -> str:
    """Detect text encoding from raw byte sequence using BOM checks.

    Args:
        data: Raw bytes of the file.

    Returns:
        Detected encoding string name.
    """
    if not data:
        return "utf-8"

    # Check Byte Order Marks (BOM)
    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if data.startswith(b"\xff\xfe\x00\x00"):
        return "utf-32-le"
    if data.startswith(b"\x00\x00\xfe\xff"):
        return "utf-32-be"
    if data.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if data.startswith(b"\xfe\xff"):
        return "utf-16-be"

    # Check ASCII
    if all(b < 128 for b in data):
        return "ascii"

    # Try strict UTF-8
    try:
        data.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass

    # Try strict UTF-16
    try:
        data.decode("utf-16")
        return "utf-16"
    except (UnicodeDecodeError, ValueError):
        pass

    # Try Windows-1252 / CP1252 vs ISO-8859-1 (Latin-1)
    # Check if bytes are valid CP1252
    try:
        data.decode("cp1252")
        return "windows-1252"
    except UnicodeDecodeError:
        pass

    # Fallback to latin-1 (which maps all 256 bytes)
    return "latin-1"


def convert_file_encoding(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    target_encoding: str = "utf-8",
    errors: str = "replace",
    source_encoding: Optional[str] = None,
) -> Tuple[str, int]:
    """Convert a single text file to target encoding.

    Args:
        input_path: Path to source file.
        output_path: Path to destination file.
        target_encoding: Desired text encoding.
        errors: Error handling mode ('strict', 'ignore', 'replace').
        source_encoding: If supplied, skips automatic detection.

    Returns:
        Tuple of (source encoding used, bytes written).
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    with open(input_path, "rb") as infile:
        raw_bytes = infile.read()

    if source_encoding:
        detected = source_encoding
    else:
        detected = detect_encoding(raw_bytes)

    # Decode text using source encoding
    text = raw_bytes.decode(detected, errors=errors)

    # Prepare output path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Encode to target encoding
    encoded_bytes = text.encode(target_encoding, errors=errors)

    with open(output_path, "wb") as outfile:
        outfile.write(encoded_bytes)

    return detected, len(encoded_bytes)


def bulk_convert_encoding(
    input_dir: Union[str, Path],
    output_dir: Union[str, Path],
    pattern: str = "*",
    target_encoding: str = "utf-8",
    errors: str = "replace",
    source_encoding: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Convert multiple files in a directory matching a pattern.

    Args:
        input_dir: Source folder path.
        output_dir: Output folder path.
        pattern: Glob pattern matching files (e.g., '*.txt').
        target_encoding: Desired target encoding.
        errors: Error handling mode.
        source_encoding: Optional manual source encoding override.

    Returns:
        List of dicts containing conversion summary per file.
    """
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    results = []

    matching_files = [p for p in input_dir.rglob(pattern) if p.is_file()]

    for file_path in matching_files:
        rel_path = file_path.relative_to(input_dir)
        out_file_path = output_dir / rel_path

        src_enc, bytes_count = convert_file_encoding(
            input_path=file_path,
            output_path=out_file_path,
            target_encoding=target_encoding,
            errors=errors,
            source_encoding=source_encoding,
        )

        results.append(
            {
                "source_path": str(file_path),
                "output_path": str(out_file_path),
                "detected_encoding": src_enc,
                "target_encoding": target_encoding,
                "bytes_written": str(bytes_count),
            }
        )

    return results


def build_parser() -> argparse.ArgumentParser:
    """Build command-line parser."""
    desc = "Text Encoding Converter & Detector Utility"
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("input", help="Input file or directory (if --bulk specified)")
    parser.add_argument("output", help="Output file or directory (if --bulk specified)")
    parser.add_argument(
        "--target",
        "-t",
        default="utf-8",
        help="Target encoding (default: utf-8)",
    )
    parser.add_argument(
        "--source",
        "-s",
        help="Force explicit source encoding instead of auto-detection",
    )
    parser.add_argument(
        "--errors",
        "-e",
        choices=["strict", "ignore", "replace"],
        default="replace",
        help="Decoding/encoding error handling strategy (default: replace)",
    )
    parser.add_argument(
        "--bulk",
        action="store_true",
        help="Treat input and output as directories for bulk conversion",
    )
    parser.add_argument(
        "--pattern",
        default="*",
        help="Glob pattern for matching files in bulk mode (default: '*')",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for text-encoding-converter."""
    parser = build_parser()
    parsed_args = parser.parse_args(args)

    try:
        if parsed_args.bulk:
            results = bulk_convert_encoding(
                input_dir=parsed_args.input,
                output_dir=parsed_args.output,
                pattern=parsed_args.pattern,
                target_encoding=parsed_args.target,
                errors=parsed_args.errors,
                source_encoding=parsed_args.source,
            )
            msg = (
                f"Bulk conversion completed. Converted {len(results)} files "
                f"to {parsed_args.target}."
            )
            print(msg)
        else:
            detected, written = convert_file_encoding(
                input_path=parsed_args.input,
                output_path=parsed_args.output,
                target_encoding=parsed_args.target,
                errors=parsed_args.errors,
                source_encoding=parsed_args.source,
            )
            msg = (
                f"Converted '{parsed_args.input}' ({detected}) -> "
                f"'{parsed_args.output}' ({parsed_args.target}, "
                f"{written} bytes)."
            )
            print(msg)
    except (OSError, ValueError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
