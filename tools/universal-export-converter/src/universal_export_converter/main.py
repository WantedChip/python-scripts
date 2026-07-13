"""Universal Export Converter main driver."""

import argparse
import csv
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

from universal_export_converter.plugins.google_takeout import (
    GoogleTakeoutConverterPlugin,
)
from universal_export_converter.plugins.slack import SlackConverterPlugin
from universal_export_converter.plugins.whatsapp import WhatsappConverterPlugin

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger("universal_export_converter")


def get_plugins() -> Dict[str, Any]:
    """Retrieve mapping of available converter plugins."""
    return {
        "slack": SlackConverterPlugin(),
        "google-takeout": GoogleTakeoutConverterPlugin(),
        "whatsapp": WhatsappConverterPlugin(),
    }


def auto_detect_plugin(file_path: Path) -> str:
    """Detect the correct plugin for the input file.

    Returns:
        Plugin name or empty string if no match found.
    """
    plugins = get_plugins()
    for name, plugin in plugins.items():
        if plugin.detect(file_path):
            logger.info("Auto-detected format: %s", name)
            return name
    return ""


def write_csv(data: List[Dict[str, Any]], output_path: Path) -> None:
    """Write normalized data as CSV."""
    fields = ["timestamp", "source", "author", "content"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in data:
            writer.writerow({k: row.get(k, "") for k in fields})


def write_json(data: List[Dict[str, Any]], output_path: Path) -> None:
    """Write normalized data as JSON."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main() -> None:  # pylint: disable=too-many-branches,too-many-statements
    """CLI execution entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Universal Export Converter — normalize " "exports from various platforms."
        )
    )
    parser.add_argument("input_path", type=str, help="Path to input export file.")
    parser.add_argument(
        "-o", "--output-path", type=str, help="Path to write converted output file."
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["json", "csv"],
        help="Output format (defaults to json or deduced from output filename).",
    )
    parser.add_argument(
        "-s",
        "--service",
        choices=["slack", "google-takeout", "whatsapp"],
        help="Explicitly choose input service type. (otherwise auto-detected)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose debug logging."
    )

    # Allow custom options or test mode parameter parsing
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    input_file = Path(args.input_path)
    if not input_file.is_file():
        logger.error("Input path does not exist or is not a file: %s", input_file)
        sys.exit(1)

    # Determine service type
    service = args.service
    if not service:
        service = auto_detect_plugin(input_file)
        if not service:
            logger.error("Could not auto-detect format. Specify manually with -s.")
            sys.exit(1)
    else:
        logger.debug("Using explicitly specified service: %s", service)

    # Run conversion
    plugins = get_plugins()
    plugin = plugins[service]

    logger.info("Normalizing export using %s plugin...", service)
    normalized_data = plugin.convert(input_file)
    logger.info("Found %d normalized records.", len(normalized_data))

    if not normalized_data:
        logger.warning(
            "No records were converted. " + "The input might be empty or malformed."
        )

    # Determine format
    out_format = args.format
    if not out_format:
        if args.output_path:
            suffix = Path(args.output_path).suffix.lower()
            out_format = "csv" if suffix == ".csv" else "json"
        else:
            out_format = "json"

    # Write output
    if args.output_path:
        out_path = Path(args.output_path)
        logger.info("Writing output to %s as %s...", out_path, out_format)
        try:
            if out_format == "csv":
                write_csv(normalized_data, out_path)
            else:
                write_json(normalized_data, out_path)
            logger.info("Conversion complete.")
        except OSError as e:
            logger.error("Failed to write output file: %s", e)
            sys.exit(1)
    else:
        # Print to stdout
        if out_format == "csv":
            writer = csv.DictWriter(
                sys.stdout,
                fieldnames=["timestamp", "source", "author", "content"],
            )
            writer.writeheader()
            for row in normalized_data:
                writer.writerow(row)
        else:
            json.dump(normalized_data, sys.stdout, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
