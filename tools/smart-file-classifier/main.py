"""Smart File Classifier Tool.

Inspects file magic numbers / MIME headers to classify files independent of
their extensions, optionally corrects mislabeled file extensions, and routes
files into category-based folders.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods
# pylint: disable=too-many-nested-blocks,too-many-return-statements

import argparse
import json
import logging
import pathlib
import shutil
import sys
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Tuple

# Comprehensive signature directory linking category, primary extension,
# and magic signatures
SIGNATURES: Dict[str, Dict[str, List[bytes]]] = {
    "images": {
        ".png": [b"\x89PNG\r\n\x1a\n"],
        ".jpg": [b"\xff\xd8\xff"],
        ".gif": [b"GIF87a", b"GIF89a"],
        ".bmp": [b"BM"],
        ".webp": [b"RIFF"],  # RIFF....WEBP
    },
    "documents": {
        ".pdf": [b"%PDF-"],
        ".xml": [b"<?xml", b"\xfe\xff<?xml", b"\xff\xfe<?xml"],
        ".html": [b"<!DOCTYPE html", b"<!doctype html", b"<html"],
    },
    "archives": {
        ".zip": [b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"],
        ".gz": [b"\x1f\x8b"],
        ".bz2": [b"BZh"],
        ".7z": [b"7z\xbc\xaf\x27\x1c"],
        ".rar": [b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00"],
    },
    "executables": {
        ".exe": [b"MZ"],
        ".elf": [b"\x7fELF"],
    },
    "audio": {
        ".mp3": [b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"],
        ".wav": [b"RIFF"],  # Note: WAV and WEBP both start with RIFF
        ".ogg": [b"OggS"],
        ".flac": [b"fLaC"],
    },
}

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("SmartFileClassifier")


@dataclass
class ClassificationRecord:
    """Record of a classified and processed file."""

    source_path: str
    destination_path: str
    detected_category: str
    detected_extension: Optional[str]
    original_extension: str
    extension_corrected: bool
    operation: str


class BinaryHeaderMatcher:
    """Binary signature pattern matching for classification."""

    @staticmethod
    def classify_file(
        file_path: pathlib.Path,
    ) -> Tuple[str, Optional[str]]:
        """Determine file category and suggested extension from magic header bytes.

        Args:
            file_path: Target file path.

        Returns:
            Tuple of (category_string, canonical_extension or None)
        """
        try:
            with open(file_path, "rb") as f:
                header = f.read(32)
        except OSError:
            return "unknown", None

        if not header:
            return "unknown", None

        for category, ext_dict in SIGNATURES.items():
            for ext, sig_list in ext_dict.items():
                for sig in sig_list:
                    if header.startswith(sig):
                        # Special disambiguation for RIFF (WAV vs WEBP)
                        if sig == b"RIFF" and len(header) >= 12:
                            if header[8:12] == b"WEBP":
                                return "images", ".webp"
                            if header[8:12] == b"WAVE":
                                return "audio", ".wav"
                        return category, ext

        # Fallback to plain text check if printable ASCII/UTF-8
        try:
            header.decode("utf-8")
            return "documents", ".txt"
        except UnicodeDecodeError:
            pass

        return "unknown", None


class FileClassifier:
    """Orchestrates file classification, extension correction, and routing."""

    def __init__(
        self,
        target_dir: pathlib.Path,
        mode: str = "copy",
        fix_extensions: bool = False,
        dry_run: bool = False,
    ):
        """Initialize classifier.

        Args:
            target_dir: Output base directory for category folders.
            mode: 'copy' or 'move'.
            fix_extensions: If True, change extension if mislabeled.
            dry_run: If True, do not perform file operations.
        """
        self.target_dir = target_dir
        self.mode = mode
        self.fix_extensions = fix_extensions
        self.dry_run = dry_run
        self.records: List[ClassificationRecord] = []

    def process_file(self, file_path: pathlib.Path) -> ClassificationRecord:
        """Classify and route a single file.

        Args:
            file_path: Path of file to classify.

        Returns:
            ClassificationRecord with operation outcome.
        """
        category, canonical_ext = BinaryHeaderMatcher.classify_file(file_path)
        orig_ext = file_path.suffix.lower()

        target_name = file_path.name
        extension_corrected = False

        if self.fix_extensions and canonical_ext and orig_ext != canonical_ext:
            target_name = file_path.stem + canonical_ext
            extension_corrected = True

        category_folder = self.target_dir / category
        dest_file = category_folder / target_name

        rec = ClassificationRecord(
            source_path=str(file_path),
            destination_path=str(dest_file),
            detected_category=category,
            detected_extension=canonical_ext,
            original_extension=orig_ext,
            extension_corrected=extension_corrected,
            operation="dry_run" if self.dry_run else self.mode,
        )

        if not self.dry_run:
            category_folder.mkdir(parents=True, exist_ok=True)
            if self.mode == "move":
                shutil.move(str(file_path), str(dest_file))
            else:
                shutil.copy2(str(file_path), str(dest_file))

        self.records.append(rec)
        logger.info(
            "[%s] %s -> %s/%s (Category: %s, Fixed Ext: %s)",
            rec.operation.upper(),
            file_path.name,
            category,
            target_name,
            category,
            extension_corrected,
        )
        return rec

    def process_directory(self, source_dir: pathlib.Path) -> List[ClassificationRecord]:
        """Classify all files in source directory.

        Args:
            source_dir: Directory containing input files.

        Returns:
            List of classification records.
        """
        for item in source_dir.rglob("*"):
            if item.is_file() and not item.is_relative_to(self.target_dir):
                self.process_file(item)
        return self.records


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Classify files by magic header signatures independent of extensions."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "source",
        type=pathlib.Path,
        help="Source directory or file to classify",
    )
    parser.add_argument(
        "output_dir",
        type=pathlib.Path,
        help="Base output directory for categorized files",
    )
    parser.add_argument(
        "--mode",
        choices=["copy", "move"],
        default="copy",
        help="File action (default: copy)",
    )
    parser.add_argument(
        "--fix-extensions",
        action="store_true",
        help="Rename files to match header detected extensions if mislabeled",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview classification without modifying files",
    )
    parser.add_argument(
        "--log-file",
        type=pathlib.Path,
        help="Path to write classification JSON log",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    if not parsed.source.exists():
        logger.error("Source path does not exist: %s", parsed.source)
        return 1

    classifier = FileClassifier(
        target_dir=parsed.output_dir,
        mode=parsed.mode,
        fix_extensions=parsed.fix_extensions,
        dry_run=parsed.dry_run,
    )

    if parsed.source.is_file():
        classifier.process_file(parsed.source)
    else:
        classifier.process_directory(parsed.source)

    if parsed.log_file:
        try:
            with open(parsed.log_file, "w", encoding="utf-8") as f:
                json.dump([asdict(r) for r in classifier.records], f, indent=2)
            logger.info("Classification log saved to: %s", parsed.log_file)
        except OSError as e:
            logger.error("Failed to write log file: %s", e)

    return 0


if __name__ == "__main__":
    sys.exit(main())
