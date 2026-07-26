"""File Extension Changer Tool.

Safely changes file extensions in bulk with magic number / file header content
validation to prevent incorrect extension assignment and repair mislabeled
files.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods
# pylint: disable=logging-fstring-interpolation,too-many-return-statements

import argparse
import logging
import pathlib
import sys
from typing import Dict, List, Optional, Tuple

# Common magic byte signatures mapping extensions to byte sequences
MAGIC_SIGNATURES: Dict[str, List[bytes]] = {
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".gif": [b"GIF87a", b"GIF89a"],
    ".pdf": [b"%PDF-"],
    ".zip": [b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"],
    ".gz": [b"\x1f\x8b"],
    ".tar.gz": [b"\x1f\x8b"],
    ".bz2": [b"BZh"],
    ".exe": [b"MZ"],
    ".dll": [b"MZ"],
    ".elf": [b"\x7fELF"],
    ".bmp": [b"BM"],
    ".wav": [b"RIFF"],
    ".ogg": [b"OggS"],
    ".mp3": [b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"],
    ".xml": [b"<?xml", b"\xfe\xff<?xml", b"\xff\xfe<?xml"],
    ".html": [b"<!DOCTYPE html", b"<!doctype html", b"<html"],
}

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("FileExtensionChanger")


class HeaderValidator:
    """Validates file contents against binary magic signatures."""

    @staticmethod
    def read_header(file_path: pathlib.Path, num_bytes: int = 32) -> bytes:
        """Read the initial header bytes from a file.

        Args:
            file_path: Path to the target file.
            num_bytes: Number of bytes to read from file head.

        Returns:
            Header bytes, or empty bytes if file cannot be read.
        """
        try:
            with open(file_path, "rb") as f:
                return f.read(num_bytes)
        except OSError as e:
            logger.warning(f"Could not read header for {file_path}: {e}")
            return b""

    @classmethod
    def detect_extension(cls, file_path: pathlib.Path) -> Optional[str]:
        """Detect probable extension for file based on magic bytes.

        Args:
            file_path: Path to the target file.

        Returns:
            Matching extension string (e.g. '.png') or None if unrecognized.
        """
        header = cls.read_header(file_path)
        if not header:
            return None

        for ext, signatures in MAGIC_SIGNATURES.items():
            for sig in signatures:
                if header.startswith(sig):
                    return ext
        return None

    @classmethod
    def validate_extension(cls, file_path: pathlib.Path, target_ext: str) -> bool:
        """Check if file header matches target extension.

        Args:
            file_path: Path to file.
            target_ext: Proposed extension (e.g. '.png' or 'png').

        Returns:
            True if signature matches or unvalidated, False if mismatch.
        """
        if not target_ext.startswith("."):
            target_ext = f".{target_ext}"
        target_ext = target_ext.lower()

        header = cls.read_header(file_path)
        signatures = MAGIC_SIGNATURES.get(target_ext)

        if not signatures:
            # Unknown magic signature, assume valid or unvalidated
            return True

        return any(header.startswith(sig) for sig in signatures)


class FileExtensionChanger:
    """Manages batch file extension changes with validation."""

    def __init__(self, dry_run: bool = False, force: bool = False):
        """Initialize the extension changer.

        Args:
            dry_run: If True, do not rename files on disk.
            force: If True, change extension even if magic number mismatches.
        """
        self.dry_run = dry_run
        self.force = force

    def change_extension(
        self, file_path: pathlib.Path, target_ext: str
    ) -> Tuple[bool, str]:
        """Change extension of a single file safely.

        Args:
            file_path: Path to the target file.
            target_ext: New extension to apply (e.g. '.jpg').

        Returns:
            Tuple of (success_boolean, message).
        """
        if not file_path.exists() or not file_path.is_file():
            return False, f"File not found: {file_path}"

        if not target_ext.startswith("."):
            target_ext = f".{target_ext}"

        current_ext = file_path.suffix.lower()
        if current_ext == target_ext.lower():
            msg = f"File {file_path.name} already has target extension " f"{target_ext}"
            return True, msg

        # Magic number check
        is_valid = HeaderValidator.validate_extension(file_path, target_ext)
        detected_ext = HeaderValidator.detect_extension(file_path)

        if not is_valid and not self.force:
            det_str = f" (detected header: {detected_ext})" if detected_ext else ""
            msg = (
                f"SKIPPED {file_path.name}: Magic bytes mismatch for "
                f"extension {target_ext}{det_str}. Use --force to override."
            )
            logger.warning(msg)
            return False, msg

        new_path = file_path.with_suffix(target_ext)

        if new_path.exists():
            return False, f"Target path already exists: {new_path}"

        if self.dry_run:
            msg = f"[DRY-RUN] Rename {file_path} -> {new_path}"
            logger.info(msg)
            return True, msg

        try:
            file_path.rename(new_path)
            msg = f"Renamed {file_path.name} -> {new_path.name}"
            logger.info(msg)
            return True, msg
        except OSError as e:
            msg = f"Error renaming {file_path}: {e}"
            logger.error(msg)
            return False, msg

    def batch_process(
        self, target_dir: pathlib.Path, target_ext: str, pattern: str = "*"
    ) -> Dict[str, int]:
        """Process directory files matching pattern.

        Args:
            target_dir: Directory containing files to rename.
            target_ext: Target extension.
            pattern: Glob pattern to filter target files.

        Returns:
            Dictionary with counts of successful and failed renames.
        """
        stats = {"success": 0, "skipped": 0, "failed": 0}
        if not target_dir.is_dir():
            logger.error(f"Invalid directory: {target_dir}")
            return stats

        for file_path in target_dir.glob(pattern):
            if file_path.is_file():
                success, _ = self.change_extension(file_path, target_ext)
                if success:
                    stats["success"] += 1
                else:
                    stats["skipped"] += 1

        return stats


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = (
        "Safely change file extensions in bulk with magic number "
        + "header validation."
    )
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("path", type=pathlib.Path, help="Target file or directory path")
    parser.add_argument(
        "-e",
        "--extension",
        required=True,
        type=str,
        help="Target extension (e.g. .png or png)",
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="*",
        help="Glob pattern when path is directory (default: '*')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without renaming files",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass header validation warning and force rename",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """Main execution entrypoint."""
    parser = build_parser()
    parsed = parser.parse_args(args)
    changer = FileExtensionChanger(dry_run=parsed.dry_run, force=parsed.force)

    if parsed.path.is_file():
        success, msg = changer.change_extension(parsed.path, parsed.extension)
        print(msg)
        return 0 if success else 1
    if parsed.path.is_dir():
        stats = changer.batch_process(parsed.path, parsed.extension, parsed.pattern)
        print(f"Batch processing completed: {stats}")
        return 0

    logger.error(f"Path does not exist: {parsed.path}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
