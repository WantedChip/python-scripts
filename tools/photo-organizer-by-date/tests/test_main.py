"""Unit tests for photo-organizer-by-date."""

import io
import os
import shutil
import struct
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from unittest.mock import patch

import main as main_module
from main import (
    build_parser,
    compute_file_hash,
    format_subfolder_path,
    get_photo_date,
    main,
    organize_photos,
    parse_exif_date_raw,
    parse_tiff_header,
)


def _entry(endian: str, tag: int, typ: int, count: int, value: bytes) -> bytes:
    """Build one 12-byte TIFF IFD entry."""
    return struct.pack(f"{endian}HHI", tag, typ, count) + value


def _tiff_blob(
    endian: str = "<",
    magic: int = 42,
    byte_order: bytes = b"II",
    ifd0_date: Optional[str] = "2021:07:04 12:30:00",
    exif_date: Optional[str] = None,
) -> bytes:
    """Assemble a minimal TIFF blob with an optional Exif sub-IFD."""
    entries = b""
    n_entries = (1 if ifd0_date is not None else 0) + (
        1 if exif_date is not None else 0
    )
    ifd0_len = 2 + 12 * n_entries + 4
    date0_offset = 8 + ifd0_len
    exif_ifd_offset = date0_offset + 20
    exif_date_offset = exif_ifd_offset + 18

    if ifd0_date is not None:
        entries += _entry(
            endian, 0x0132, 2, 20, struct.pack(f"{endian}I", date0_offset)
        )
        n_entries += 1
    if exif_date is not None:
        entries += _entry(
            endian, 0x8769, 4, 1, struct.pack(f"{endian}I", exif_ifd_offset)
        )
        n_entries += 1

    blob = byte_order + struct.pack(f"{endian}H", magic)
    blob += struct.pack(f"{endian}I", 8)
    blob += struct.pack(f"{endian}H", n_entries) + entries
    blob += struct.pack(f"{endian}I", 0)
    blob += (ifd0_date or "").encode("ascii").ljust(20, b"\x00")
    if exif_date is not None:
        blob += struct.pack(f"{endian}H", 1)
        blob += _entry(
            endian, 0x9003, 2, 20, struct.pack(f"{endian}I", exif_date_offset)
        )
        blob += struct.pack(f"{endian}I", 0)
        blob += exif_date.encode("ascii").ljust(20, b"\x00")
    return blob


def _wrap_app1(tiff_bytes: bytes) -> bytes:
    """Wrap a TIFF payload into a minimal JPEG with an APP1/Exif segment."""
    payload = b"Exif\x00\x00" + tiff_bytes
    segment = b"\xff\xd8\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload
    return segment + b"\xff\xd9"


class TestPhotoOrganizer(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.source_dir = Path(self.temp_dir) / "photos"
        self.dest_dir = Path(self.temp_dir) / "organized"
        self.source_dir.mkdir()

        # Create dummy image file
        self.img1 = self.source_dir / "photo1.jpg"
        header = (
            b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00\x60\x00\x60"
            b"\x00\x00\xFF\xD9"
        )
        self.img1.write_bytes(header)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_format_subfolder_path(self):
        dt = datetime(2023, 5, 17, 14, 30, 0)
        self.assertEqual(format_subfolder_path(dt, "YYYY/MM"), Path("2023/05"))
        self.assertEqual(format_subfolder_path(dt, "YYYY-MM-DD"), Path("2023-05-17"))
        self.assertEqual(format_subfolder_path(dt, "YYYY/MM/DD"), Path("2023/05/17"))

    def test_format_subfolder_path_custom_strftime(self):
        """Non-preset formats are passed through as strftime directives."""
        dt = datetime(2023, 5, 17, 14, 30, 0)
        self.assertEqual(format_subfolder_path(dt, "%Y_%m"), Path("2023_05"))

    def test_get_photo_date_fallback(self):
        dt = get_photo_date(self.img1)
        self.assertIsInstance(dt, datetime)

    def test_organize_photos_copy(self):
        results = organize_photos(
            source_dir=self.source_dir,
            dest_dir=self.dest_dir,
            folder_format="YYYY/MM",
            mode="copy",
        )
        self.assertEqual(len(results), 1)
        self.assertTrue(self.img1.exists())  # Source remains in copy mode
        dest_files = list(self.dest_dir.rglob("*.jpg"))
        self.assertEqual(len(dest_files), 1)

    def test_organize_photos_move(self):
        results = organize_photos(
            source_dir=self.source_dir,
            dest_dir=self.dest_dir,
            folder_format="YYYY-MM-DD",
            mode="move",
        )
        self.assertEqual(len(results), 1)
        self.assertFalse(self.img1.exists())  # Source moved
        dest_files = list(self.dest_dir.rglob("*.jpg"))
        self.assertEqual(len(dest_files), 1)


class TestRawExifParsing(unittest.TestCase):
    """Test suite for the pure-Python EXIF binary parser."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.work = Path(self.tmp_dir.name)

    def _write_jpg(self, name: str, data: bytes) -> Path:
        path = self.work / name
        path.write_bytes(data)
        return path

    def test_little_endian_ifd0_datetime_is_parsed(self) -> None:
        jpeg = _wrap_app1(_tiff_blob(endian="<", byte_order=b"II"))
        path = self._write_jpg("le.jpg", jpeg)
        parsed = parse_exif_date_raw(path)
        assert parsed is not None
        self.assertEqual(parsed.replace(tzinfo=None), datetime(2021, 7, 4, 12, 30))

    def test_big_endian_ifd0_datetime_is_parsed(self) -> None:
        jpeg = _wrap_app1(_tiff_blob(endian=">", byte_order=b"MM"))
        path = self._write_jpg("be.jpg", jpeg)
        parsed = parse_exif_date_raw(path)
        assert parsed is not None
        self.assertEqual(parsed.replace(tzinfo=None), datetime(2021, 7, 4, 12, 30))

    def test_exif_subifd_pointer_is_followed(self) -> None:
        tiff = _tiff_blob(ifd0_date=None, exif_date="2020:01:02 03:04:05")
        path = self._write_jpg("sub.jpg", _wrap_app1(tiff))
        parsed = parse_exif_date_raw(path)
        assert parsed is not None
        self.assertEqual(parsed.replace(tzinfo=None), datetime(2020, 1, 2, 3, 4, 5))

    def test_non_jpeg_suffix_returns_none(self) -> None:
        path = self.work / "image.png"
        path.write_bytes(b"\xff\xd8\xff\xe1" + b"\x00" * 20 + b"\xff\xd9")
        self.assertIsNone(parse_exif_date_raw(path))

    def test_invalid_jpeg_magic_returns_none(self) -> None:
        path = self._write_jpg("fake.jpg", b"MZ" + b"\x00" * 24)
        self.assertIsNone(parse_exif_date_raw(path))

    def test_scan_skips_fill_bytes_between_markers(self) -> None:
        jpeg = _wrap_app1(_tiff_blob())
        padded = jpeg[:2] + b"\x00\x00\x00" + jpeg[2:]
        path = self._write_jpg("padded.jpg", padded)
        parsed = parse_exif_date_raw(path)
        assert parsed is not None
        self.assertEqual(parsed.year, 2021)

    def test_parsing_stops_at_sos_marker(self) -> None:
        truncated = b"\xff\xd8\xff\xda" + b"\x00" * 16
        path = self._write_jpg("sos.jpg", truncated)
        self.assertIsNone(parse_exif_date_raw(path))

    def test_unreadable_file_returns_none(self) -> None:
        dir_named_jpg = self.work / "weird.jpg"
        dir_named_jpg.mkdir()
        self.assertIsNone(parse_exif_date_raw(dir_named_jpg))


class TestTiffHeaderEdgeCases(unittest.TestCase):
    """Direct unit tests for TIFF header validation."""

    def test_too_short_blob_rejected(self) -> None:
        self.assertIsNone(parse_tiff_header(b"II\x00"))

    def test_unknown_byte_order_rejected(self) -> None:
        self.assertIsNone(parse_tiff_header(b"XX" + b"\x00" * 10))

    def test_bad_magic_number_rejected(self) -> None:
        blob = _tiff_blob(magic=43)[:8] + b"\x00" * 24
        self.assertIsNone(parse_tiff_header(blob))

    def test_garbage_date_value_returns_none(self) -> None:
        blob = _tiff_blob(ifd0_date="garbage here!!!!!!!!")
        self.assertIsNone(parse_tiff_header(blob))


class TestGetPhotoDateSources(unittest.TestCase):
    """Test suite for EXIF-first date resolution with PIL fakes."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.work = Path(self.tmp_dir.name)

    def test_exif_datetime_wins_over_mtime(self) -> None:
        target = self.work / "withexif.jpg"
        target.write_bytes(b"\xff\xd8" + b"\x00" * 16)

        fake_img = SimpleNamespace(_getexif=lambda: {306: "2021:07:04 12:30:00"})
        fake_image = SimpleNamespace(open=lambda _p: _NullContext(fake_img))
        fake_tags = SimpleNamespace(TAGS={306: "DateTime"})
        with patch.object(main_module, "HAS_PIL", True), patch.object(
            main_module, "Image", fake_image
        ), patch.object(main_module, "ExifTags", fake_tags):
            dt = get_photo_date(target)
        self.assertEqual(dt, datetime(2021, 7, 4, 12, 30))

    def test_pil_failure_falls_back_to_binary_parser(self) -> None:
        target = self.work / "rawexif.jpg"
        target.write_bytes(_wrap_app1(_tiff_blob()))

        def boom(_path: str) -> None:
            raise RuntimeError("PIL exploded")

        fake_image = SimpleNamespace(open=boom)
        with patch.object(main_module, "HAS_PIL", True), patch.object(
            main_module, "Image", fake_image
        ):
            dt = get_photo_date(target)
        self.assertEqual(dt.year, 2021)


class _NullContext:
    """Minimal context manager standing in for PIL's Image.open result."""

    def __init__(self, value: object) -> None:
        self._value = value

    def __enter__(self) -> object:
        return self._value

    def __exit__(self, *_args: object) -> None:
        return None


class TestOrganizeCollisionHandling(unittest.TestCase):
    """Test suite for duplicate handling and dry-run behavior."""

    JPEG_BLOB = (
        b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00\x60\x00\x60"
        b"\x00\x00\xFF\xD9"
    )

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.source = Path(self.tmp_dir.name) / "src"
        self.dest = Path(self.tmp_dir.name) / "dest"
        self.source.mkdir()

    def _add_photo(self, name: str, content: bytes = JPEG_BLOB) -> Path:
        path = self.source / name
        path.write_bytes(content)
        stamp = datetime(2021, 7, 4, 12, 0).timestamp()
        os.utime(path, (stamp, stamp))
        return path

    def _target(self, name: str) -> Path:
        return self.dest / "2021" / "07" / name

    def test_unsupported_extensions_are_ignored(self) -> None:
        (self.source / "notes.txt").write_text("hello")
        results = organize_photos(
            source_dir=self.source, dest_dir=self.dest, folder_format="YYYY/MM"
        )
        self.assertEqual(results, [])

    def test_dry_run_creates_nothing_but_reports(self) -> None:
        self._add_photo("photo1.jpg")
        results = organize_photos(
            source_dir=self.source,
            dest_dir=self.dest,
            folder_format="YYYY/MM",
            dry_run=True,
        )
        self.assertEqual(results[0]["action"], "copy_dry_run")
        self.assertFalse(any(self.dest.rglob("*")))

    def test_collision_skip_leaves_target_untouched(self) -> None:
        src = self._add_photo("photo1.jpg", b"NEW CONTENT")
        target = self._target("photo1.jpg")
        target.parent.mkdir(parents=True)
        target.write_bytes(b"OLD ORIGINAL")

        results = organize_photos(
            source_dir=self.source,
            dest_dir=self.dest,
            folder_format="YYYY/MM",
            collision_action="skip",
        )
        self.assertEqual(results[0]["status"], "skipped_duplicate")
        self.assertTrue(src.exists())
        self.assertEqual(target.read_bytes(), b"OLD ORIGINAL")

    def test_identical_file_is_skipped_via_hash(self) -> None:
        self._add_photo("photo1.jpg")
        results = organize_photos(
            source_dir=self.source, dest_dir=self.dest, folder_format="YYYY/MM"
        )
        self.assertEqual(len(results), 1)
        # Second run sees the identical copy already in place.
        results2 = organize_photos(
            source_dir=self.source,
            dest_dir=self.dest,
            folder_format="YYYY/MM",
            collision_action="rename",
        )
        self.assertEqual(results2[0]["status"], "skipped_identical")

    def test_different_content_gets_renamed(self) -> None:
        src = self._add_photo("photo1.jpg")
        first = organize_photos(
            source_dir=self.source, dest_dir=self.dest, folder_format="YYYY/MM"
        )
        self.assertEqual(first[0]["status"], "success")

        # Same name and date folder, but different content now.
        # (write_bytes resets mtime, so re-stamp to hit the same folder.)
        src.write_bytes(b"different bytes entirely")
        stamp = datetime(2021, 7, 4, 12, 0).timestamp()
        os.utime(src, (stamp, stamp))

        results = organize_photos(
            source_dir=self.source,
            dest_dir=self.dest,
            folder_format="YYYY/MM",
            collision_action="rename",
        )
        self.assertEqual(len(results), 1)
        renamed = results[0]
        self.assertTrue(renamed["dest"].endswith("photo1_1.jpg"))
        self.assertTrue(Path(renamed["dest"]).exists())

    def test_copy_failure_is_reported_in_record(self) -> None:
        self._add_photo("photo1.jpg")
        with patch.object(
            main_module.shutil, "copy2", side_effect=OSError("disk full")
        ):
            results = organize_photos(
                source_dir=self.source, dest_dir=self.dest, folder_format="YYYY/MM"
            )
        self.assertTrue(results[0]["status"].startswith("failed:"))

    def test_date_error_skips_file_gracefully(self) -> None:
        photo = self._add_photo("photo1.jpg")
        with patch.object(
            main_module, "get_photo_date", side_effect=ValueError("bad exif")
        ):
            results = organize_photos(
                source_dir=self.source, dest_dir=self.dest, folder_format="YYYY/MM"
            )
        self.assertEqual(results, [])
        self.assertTrue(photo.exists())


class TestHashingAndCli(unittest.TestCase):
    """Tests for file hashing plus build_parser/main wiring."""

    def test_compute_file_hash_matches_and_differs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            f1 = base / "a.bin"
            f2 = base / "b.bin"
            f3 = base / "c.bin"
            f1.write_bytes(b"identical payload")
            f2.write_bytes(b"identical payload")
            f3.write_bytes(b"something else")
            self.assertEqual(compute_file_hash(f1), compute_file_hash(f2))
            self.assertNotEqual(compute_file_hash(f1), compute_file_hash(f3))

    def test_build_parser_flags_and_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--source", "s", "--dest", "d"])
        self.assertEqual(args.format, "YYYY/MM")
        self.assertEqual(args.mode, "copy")
        self.assertEqual(args.collision_action, "rename")
        self.assertFalse(args.dry_run)

        full = parser.parse_args(
            [
                "-s",
                "s",
                "-d",
                "d",
                "-f",
                "YYYY/MM/DD",
                "-m",
                "move",
                "--collision-action",
                "overwrite",
                "--dry-run",
            ]
        )
        self.assertEqual(full.mode, "move")
        self.assertTrue(full.dry_run)

    def test_main_reports_organized_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            src = base / "s"
            dst = base / "d"
            src.mkdir()
            (src / "pic.jpg").write_bytes(TestOrganizeCollisionHandling.JPEG_BLOB)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(
                    [
                        "--source",
                        str(src),
                        "--dest",
                        str(dst),
                        "--dry-run",
                    ]
                )
            self.assertEqual(rc, 0)
            self.assertIn("Organized 1 photos.", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
