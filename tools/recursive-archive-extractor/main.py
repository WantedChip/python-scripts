"""Recursive Archive Extractor Tool.

Recursively finds and extracts nested archives (.zip, .tar, .tar.gz, .tar.bz2)
with password list retry support and archive bomb prevention controls.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods

import argparse
import logging
import pathlib
import sys
import tarfile
import zipfile
from dataclasses import dataclass, field
from typing import List, Optional, Set

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("ArchiveExtractor")

ARCHIVE_EXTENSIONS = {
    ".zip",
    ".tar",
    ".gz",
    ".tgz",
    ".bz2",
    ".tbz2",
    ".xz",
    ".txz",
}


@dataclass
class ExtractionMetrics:
    """Track resource metrics for archive bomb prevention."""

    total_files: int = 0
    total_bytes: int = 0
    extracted_archives: Set[str] = field(default_factory=set)
    errors: List[str] = field(default_factory=list)


class ArchiveBombException(Exception):
    """Raised when extraction exceeds defined security resource thresholds."""


class RecursiveArchiveExtractor:
    """Engine for safe, recursive archive extraction."""

    def __init__(
        self,
        output_dir: pathlib.Path,
        passwords: Optional[List[str]] = None,
        max_depth: int = 5,
        max_size_mb: int = 1024,
        max_files: int = 10000,
    ):
        """Initialize extractor with security thresholds.

        Args:
            output_dir: Destination directory for extracted content.
            passwords: List of passwords for encrypted zip files.
            max_depth: Maximum recursion depth for nested archives.
            max_size_mb: Maximum total size (in MB) allowed for files.
            max_files: Maximum total number of extracted files allowed.
        """
        self.output_dir = output_dir.resolve()
        self.passwords = passwords or []
        self.max_depth = max_depth
        self.max_bytes = max_size_mb * 1024 * 1024
        self.max_files = max_files
        self.metrics = ExtractionMetrics()

    @staticmethod
    def is_safe_path(target_dir: pathlib.Path, path: pathlib.Path) -> bool:
        """Validate path against Zip Slip / path traversal attacks."""
        resolved_target = target_dir.resolve()
        resolved_path = path.resolve()
        try:
            resolved_path.relative_to(resolved_target)
            return True
        except ValueError:
            return False

    def _check_limits(
        self, additional_files: int = 1, additional_bytes: int = 0
    ) -> None:
        """Check if extraction exceeds defined bomb prevention limits."""
        if self.metrics.total_files + additional_files > self.max_files:
            err = f"Exceeded max file count threshold ({self.max_files} files)"
            raise ArchiveBombException(err)
        if self.metrics.total_bytes + additional_bytes > self.max_bytes:
            mb = self.max_bytes / (1024 * 1024)
            raise ArchiveBombException(f"Exceeded max size threshold ({mb:.1f} MB)")

    def extract_zip(self, archive_path: pathlib.Path, dest_dir: pathlib.Path) -> bool:
        """Extract ZIP archive with optional password retries and checks."""
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                pwd_bytes_list: List[Optional[bytes]] = [None] + [
                    p.encode("utf-8") for p in self.passwords
                ]
                extracted = False

                for pwd in pwd_bytes_list:
                    try:
                        for member in zf.infolist():
                            target_file = dest_dir / member.filename
                            if not self.is_safe_path(dest_dir, target_file):
                                logger.warning(
                                    "Skipping path traversal: %s",
                                    member.filename,
                                )
                                continue

                            if member.is_dir():
                                target_file.mkdir(parents=True, exist_ok=True)
                                continue

                            self._check_limits(1, member.file_size)
                            target_file.parent.mkdir(parents=True, exist_ok=True)
                            with zf.open(member, pwd=pwd) as source, open(
                                target_file, "wb"
                            ) as target:
                                while chunk := source.read(65536):
                                    target.write(chunk)

                            self.metrics.total_files += 1
                            self.metrics.total_bytes += member.file_size
                        extracted = True
                        break
                    except (RuntimeError, zipfile.BadZipFile) as e:
                        err_str = str(e).lower()
                        if "password" in err_str or "bad password" in err_str:
                            continue
                        raise e

                if not extracted:
                    msg = (
                        "Failed to decrypt zip archive (password"
                        f" required/invalid): {archive_path.name}"
                    )
                    logger.error(msg)
                    self.metrics.errors.append(msg)
                    return False

                return True
        except ArchiveBombException:
            raise
        except Exception as e:  # pylint: disable=broad-exception-caught
            msg = f"Error extracting ZIP {archive_path.name}: {e}"
            logger.error(msg)
            self.metrics.errors.append(msg)
            return False

    def extract_tar(self, archive_path: pathlib.Path, dest_dir: pathlib.Path) -> bool:
        """Extract TAR archive (.tar, .tar.gz, .tar.bz2) safely."""
        try:
            with tarfile.open(archive_path, "r:*") as tf:
                for member in tf.getmembers():
                    target_file = dest_dir / member.name
                    if not self.is_safe_path(dest_dir, target_file):
                        logger.warning("Skipping TAR path traversal: %s", member.name)
                        continue

                    if member.isdir():
                        target_file.mkdir(parents=True, exist_ok=True)
                        continue

                    self._check_limits(1, member.size)
                    tf.extract(member, path=dest_dir)
                    self.metrics.total_files += 1
                    self.metrics.total_bytes += member.size

            return True
        except ArchiveBombException:
            raise
        except Exception as e:  # pylint: disable=broad-exception-caught
            msg = f"Error extracting TAR archive {archive_path.name}: {e}"
            logger.error(msg)
            self.metrics.errors.append(msg)
            return False

    def extract_archive(
        self, archive_path: pathlib.Path, dest_dir: pathlib.Path
    ) -> bool:
        """Route and extract single archive based on extension."""
        canon_path_str = str(archive_path.resolve())
        if canon_path_str in self.metrics.extracted_archives:
            return False
        self.metrics.extracted_archives.add(canon_path_str)

        dest_dir.mkdir(parents=True, exist_ok=True)
        name_lower = archive_path.name.lower()

        if name_lower.endswith(".zip"):
            return self.extract_zip(archive_path, dest_dir)
        tar_exts = (
            ".tar",
            ".tar.gz",
            ".tgz",
            ".tar.bz2",
            ".tbz2",
            ".tar.xz",
            ".txz",
        )
        if any(name_lower.endswith(ext) for ext in tar_exts):
            return self.extract_tar(archive_path, dest_dir)
        return False

    def process_recursive(
        self, archive_path: pathlib.Path, current_depth: int = 1
    ) -> ExtractionMetrics:
        """Recursively discover and extract archives up to max_depth.

        Args:
            archive_path: Root archive file to extract.
            current_depth: Current recursion depth.

        Returns:
            ExtractionMetrics summarizing extraction results.
        """
        if current_depth > self.max_depth:
            logger.warning(
                "Reached max depth limit (%d). Stopping nested search.",
                self.max_depth,
            )
            return self.metrics

        sub_folder_name = archive_path.stem.split(".")[0]
        dest_sub_dir = self.output_dir / f"depth_{current_depth}_{sub_folder_name}"

        logger.info(
            "Extracting depth %d: %s -> %s",
            current_depth,
            archive_path.name,
            dest_sub_dir,
        )
        try:
            success = self.extract_archive(archive_path, dest_sub_dir)
        except ArchiveBombException as e:
            logger.error("Archive bomb limit triggered: %s", e)
            self.metrics.errors.append(str(e))
            return self.metrics

        if not success:
            return self.metrics

        # Scan for nested archives inside destination subfolder
        nested_archives: List[pathlib.Path] = []
        for path in dest_sub_dir.rglob("*"):
            if path.is_file():
                suffix = "".join(path.suffixes).lower()
                if any(suffix.endswith(ext) for ext in ARCHIVE_EXTENSIONS):
                    nested_archives.append(path)

        for nested in nested_archives:
            try:
                self.process_recursive(nested, current_depth=current_depth + 1)
            except ArchiveBombException as e:
                logger.error("Archive bomb limit triggered: %s", e)
                self.metrics.errors.append(str(e))
                break

        return self.metrics


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = (
        "Recursively extract nested archives with password retries and bomb"
        " protection."
    )
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "archive", type=pathlib.Path, help="Target archive file to extract"
    )
    parser.add_argument(
        "output_dir", type=pathlib.Path, help="Output destination folder"
    )
    parser.add_argument(
        "--password",
        action="append",
        help="Password for zip archive (can specify multiple)",
    )
    parser.add_argument(
        "--passwords-file",
        type=pathlib.Path,
        help="Path to text file containing password wordlist",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=5,
        help="Maximum recursion depth for nested archives (default: 5)",
    )
    parser.add_argument(
        "--max-size-mb",
        type=int,
        default=1024,
        help="Maximum total size limit in MB (default: 1024 MB)",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=10000,
        help="Maximum total file count limit (default: 10000)",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    if not parsed.archive.is_file():
        logger.error("Archive file not found: %s", parsed.archive)
        return 1

    passwords = parsed.password or []
    if parsed.passwords_file and parsed.passwords_file.is_file():
        try:
            with open(parsed.passwords_file, "r", encoding="utf-8") as f:
                passwords.extend([line.strip() for line in f if line.strip()])
        except OSError as e:
            logger.error("Failed to read password file: %s", e)

    extractor = RecursiveArchiveExtractor(
        output_dir=parsed.output_dir,
        passwords=passwords,
        max_depth=parsed.max_depth,
        max_size_mb=parsed.max_size_mb,
        max_files=parsed.max_files,
    )

    metrics = extractor.process_recursive(parsed.archive)
    print("=" * 60)
    print("EXTRACTION SUMMARY REPORT")
    print(f"Archives Extracted : {len(metrics.extracted_archives)}")
    print(f"Total Files        : {metrics.total_files}")
    mb_tot = metrics.total_bytes / (1024 * 1024)
    print(f"Total Size         : {mb_tot:.2f} MB")
    print(f"Errors Encountered : {len(metrics.errors)}")
    if metrics.errors:
        print("Error details:")
        for err in metrics.errors:
            print(f"  - {err}")
    print("=" * 60)

    return 0 if not metrics.errors else 1


if __name__ == "__main__":
    sys.exit(main())
