"""Photo Organizer by Date.

Organizes photos into folder structures (e.g. YYYY/MM or YYYY-MM-DD) based
on EXIF DateTimeOriginal metadata or file modification date fallback.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes,too-few-public-methods
# pylint: disable=protected-access

import argparse
import hashlib
import os
import shutil
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from PIL import ExifTags, Image

    HAS_PIL = True
except ImportError:
    HAS_PIL = False


SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".tiff",
    ".tif",
    ".webp",
    ".heic",
    ".cr2",
    ".nef",
    ".arw",
    ".dng",
}


def parse_exif_date_raw(file_path: Path) -> Optional[datetime]:
    """Pure-Python fallback parser for JPEG EXIF DateTimeOriginal or tags.

    Args:
        file_path: Path to the image file.

    Returns:
        datetime object if parsed successfully, otherwise None.
    """
    if file_path.suffix.lower() not in {".jpg", ".jpeg"}:
        return None

    try:
        with open(file_path, "rb") as f:
            data = f.read(65536)  # Read first 64KB for EXIF APP1 header

        if len(data) < 12 or data[:2] != b"\xff\xd8":
            return None

        pos = 2
        while pos < len(data) - 4:
            if data[pos] != 0xFF:
                pos += 1
                continue
            marker = data[pos + 1]
            if marker == 0xE1:  # APP1 marker
                length = struct.unpack(">H", data[pos + 2 : pos + 4])[0]  # noqa: E203
                app1_data = data[pos + 4 : pos + 2 + length]  # noqa: E203
                if app1_data.startswith(b"Exif\x00\x00"):
                    tiff_header = app1_data[6:]
                    return parse_tiff_header(tiff_header)
                break
            if marker in (0xD9, 0xDA):  # EOI, SOS
                break
            length = struct.unpack(">H", data[pos + 2 : pos + 4])[0]  # noqa: E203
            pos += 2 + length
    except (OSError, ValueError, struct.error):
        pass  # nosec B110

    return None


def parse_tiff_header(tiff_bytes: bytes) -> Optional[datetime]:
    """Parse TIFF header in binary EXIF data for datetime strings."""
    if len(tiff_bytes) < 8:
        return None

    byte_order = tiff_bytes[:2]
    if byte_order == b"II":
        endian = "<"
    elif byte_order == b"MM":
        endian = ">"
    else:
        return None

    magic = struct.unpack(f"{endian}H", tiff_bytes[2:4])[0]
    if magic != 42:
        return None

    ifd0_offset = struct.unpack(f"{endian}I", tiff_bytes[4:8])[0]
    exif_offset = None
    date_str = None

    def read_ifd(offset: int) -> Tuple[Optional[str], Optional[int]]:
        nonlocal tiff_bytes, endian
        if offset + 2 > len(tiff_bytes):
            return None, None

        n_ent = struct.unpack(
            f"{endian}H", tiff_bytes[offset : offset + 2]  # noqa: E203
        )[0]
        exif_ptr = None
        found_date = None

        for i in range(n_ent):
            entry_pos = offset + 2 + i * 12
            if entry_pos + 12 > len(tiff_bytes):
                break
            tag, _, count, val_offset = struct.unpack(
                f"{endian}HHII", tiff_bytes[entry_pos : entry_pos + 12]  # noqa: E203
            )

            if tag == 0x8769:  # Exif IFD Pointer
                exif_ptr = val_offset
            elif tag in (0x9003, 0x0132):  # DateTimeOriginal or DateTime
                if count >= 19 and val_offset < len(tiff_bytes):
                    raw = tiff_bytes[val_offset : val_offset + 19]  # noqa: E203
                    found_date = raw.decode("ascii", errors="ignore")

        return found_date, exif_ptr

    date_str, exif_offset = read_ifd(ifd0_offset)
    if not date_str and exif_offset:
        date_str, _ = read_ifd(exif_offset)

    if date_str:
        try:
            # Expected format: "YYYY:MM:DD HH:MM:SS"
            parts = date_str.split(" ")
            ymd = parts[0].replace(":", "-")
            hms = parts[1] if len(parts) > 1 else "00:00:00"
            return datetime.fromisoformat(f"{ymd}T{hms}")
        except (ValueError, TypeError):
            pass

    return None


def get_photo_date(file_path: Path) -> datetime:
    """Retrieve photo creation datetime from EXIF data or file mtime.

    Args:
        file_path: Image file path.

    Returns:
        datetime object.
    """
    if HAS_PIL:
        try:
            with Image.open(file_path) as img:
                exif = getattr(img, "_getexif", lambda: None)()
                if exif:
                    for tag_id, value in exif.items():
                        tag_name = ExifTags.TAGS.get(tag_id, tag_id)
                        if tag_name in ("DateTimeOriginal", "DateTime"):
                            if isinstance(value, str):
                                parts = value.strip().split(" ")
                                ymd = parts[0].replace(":", "-")
                                hms = parts[1] if len(parts) > 1 else "00:00:00"
                                return datetime.fromisoformat(f"{ymd}T{hms}")
        except Exception:  # pylint: disable=broad-exception-caught
            pass  # nosec B110

    # Try pure python binary parser
    dt = parse_exif_date_raw(file_path)
    if dt:
        return dt

    # Fallback to file mtime
    mtime = file_path.stat().st_mtime
    return datetime.fromtimestamp(mtime, tz=timezone.utc).replace(tzinfo=None)


def format_subfolder_path(dt: datetime, fmt: str) -> Path:
    """Format subfolder structure based on date and format string.

    Supported presets: 'YYYY/MM', 'YYYY-MM-DD', 'YYYY/MM/DD'.
    Also supports custom strftime directives.
    """
    if fmt == "YYYY/MM":
        return Path(dt.strftime("%Y/%m"))
    if fmt == "YYYY-MM-DD":
        return Path(dt.strftime("%Y-%m-%d"))
    if fmt == "YYYY/MM/DD":
        return Path(dt.strftime("%Y/%m/%d"))
    return Path(dt.strftime(fmt))


def compute_file_hash(file_path: Path) -> str:
    """Compute MD5 hash of a file for duplicate detection."""
    hasher = hashlib.md5()  # nosec B324
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def organize_photos(
    source_dir: Path,
    dest_dir: Path,
    folder_format: str = "YYYY/MM",
    mode: str = "copy",
    collision_action: str = "rename",
    dry_run: bool = False,
) -> List[Dict[str, str]]:
    """Scan source_dir for photos and organize them into dest_dir by date.

    Args:
        source_dir: Path to directory with images.
        dest_dir: Target root path.
        folder_format: 'YYYY/MM', 'YYYY-MM-DD', etc.
        mode: 'copy' or 'move'.
        collision_action: 'rename', 'skip', or 'overwrite'.
        dry_run: If True, do not modify files.

    Returns:
        List of log records describing operations.
    """
    source_dir = Path(source_dir).resolve()
    dest_dir = Path(dest_dir).resolve()
    records: List[Dict[str, str]] = []

    for root, _, files in os.walk(source_dir):
        for filename in files:
            file_path = Path(root) / filename
            if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            try:
                dt = get_photo_date(file_path)
            except (OSError, ValueError):
                continue

            rel_subfolder = format_subfolder_path(dt, folder_format)
            target_folder = dest_dir / rel_subfolder
            target_path = target_folder / file_path.name

            if target_path.exists():
                if collision_action == "skip":
                    records.append(
                        {
                            "source": str(file_path),
                            "dest": str(target_path),
                            "status": "skipped_duplicate",
                        }
                    )
                    continue
                if collision_action == "rename":
                    # Check if identical file
                    h1 = compute_file_hash(file_path)
                    h2 = compute_file_hash(target_path)
                    if h1 == h2:
                        records.append(
                            {
                                "source": str(file_path),
                                "dest": str(target_path),
                                "status": "skipped_identical",
                            }
                        )
                        continue
                    # Collision counter
                    stem, suffix = file_path.stem, file_path.suffix
                    counter = 1
                    while target_path.exists():
                        new_name = f"{stem}_{counter}{suffix}"
                        target_path = target_folder / new_name
                        counter += 1

            record = {
                "source": str(file_path),
                "dest": str(target_path),
                "date": dt.isoformat(),
                "action": f"{mode}{'_dry_run' if dry_run else ''}",
                "status": "success",
            }

            if not dry_run:
                target_folder.mkdir(parents=True, exist_ok=True)
                try:
                    if mode == "move":
                        shutil.move(str(file_path), str(target_path))
                    else:
                        shutil.copy2(str(file_path), str(target_path))
                except OSError as e:
                    record["status"] = f"failed: {e}"

            records.append(record)

    return records


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "Organize photos into date-based folders."
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "--source",
        "-s",
        required=True,
        type=Path,
        help="Source directory containing photos",
    )
    parser.add_argument(
        "--dest",
        "-d",
        required=True,
        type=Path,
        help="Destination directory for organized photos",
    )
    parser.add_argument(
        "--format",
        "-f",
        default="YYYY/MM",
        help="Subfolder format (YYYY/MM, YYYY-MM-DD, YYYY/MM/DD)",
    )
    parser.add_argument(
        "--mode",
        "-m",
        choices=["copy", "move"],
        default="copy",
        help="File operation mode",
    )
    parser.add_argument(
        "--collision-action",
        choices=["rename", "skip", "overwrite"],
        default="rename",
        help="Action when filename exists",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate organization without modifying filesystem",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for photo-organizer-by-date."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    results = organize_photos(
        source_dir=parsed.source,
        dest_dir=parsed.dest,
        folder_format=parsed.format,
        mode=parsed.mode,
        collision_action=parsed.collision_action,
        dry_run=parsed.dry_run,
    )

    print(f"Organized {len(results)} photos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
