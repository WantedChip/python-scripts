import pathlib
import tempfile
import unittest
from unittest.mock import patch

from main import FileExtensionChanger, HeaderValidator, build_parser, main


class TestFileExtensionChanger(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = pathlib.Path(self.temp_dir.name)

        # Create dummy PNG file with valid header
        self.png_file = self.dir_path / "test1.dat"
        self.png_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

        # Create dummy JPEG file with valid header
        self.jpg_file = self.dir_path / "test2.raw"
        self.jpg_file.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_header_validation(self):
        self.assertTrue(HeaderValidator.validate_extension(self.png_file, ".png"))
        self.assertFalse(HeaderValidator.validate_extension(self.png_file, ".pdf"))
        self.assertEqual(HeaderValidator.detect_extension(self.png_file), ".png")
        self.assertEqual(HeaderValidator.detect_extension(self.jpg_file), ".jpg")

    def test_dry_run_rename(self):
        changer = FileExtensionChanger(dry_run=True)
        success, msg = changer.change_extension(self.png_file, ".png")
        self.assertTrue(success)
        self.assertIn("[DRY-RUN]", msg)
        self.assertTrue(self.png_file.exists())  # File should not be actually renamed

    def test_actual_rename_success(self):
        changer = FileExtensionChanger(dry_run=False)
        success, msg = changer.change_extension(self.png_file, ".png")
        self.assertTrue(success)
        new_path = self.png_file.with_suffix(".png")
        self.assertTrue(new_path.exists())
        self.assertFalse(self.png_file.exists())

    def test_rename_mismatch_warning(self):
        changer = FileExtensionChanger(dry_run=False, force=False)
        # Attempt to rename PNG file as PDF (should fail validation)
        success, msg = changer.change_extension(self.jpg_file, ".pdf")
        self.assertFalse(success)
        self.assertIn("Magic bytes mismatch", msg)
        self.assertTrue(self.jpg_file.exists())

    def test_rename_force_override(self):
        changer = FileExtensionChanger(dry_run=False, force=True)
        success, msg = changer.change_extension(self.jpg_file, ".pdf")
        self.assertTrue(success)
        new_path = self.jpg_file.with_suffix(".pdf")
        self.assertTrue(new_path.exists())


PNG_HEADER = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"


class TestHeaderValidatorEdgeCases(unittest.TestCase):
    """Edge cases for header reading, detection, and validation."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = pathlib.Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_read_header_oserror_returns_empty(self) -> None:
        """An unreadable file yields empty bytes instead of raising."""
        unreadable = self.dir_path / "locked.dat"
        unreadable.write_bytes(PNG_HEADER)

        with patch("builtins.open", side_effect=PermissionError(13, "denied")):
            self.assertEqual(HeaderValidator.read_header(unreadable), b"")
            self.assertIsNone(HeaderValidator.detect_extension(unreadable))

    def test_detect_extension_empty_file_returns_none(self) -> None:
        """An empty file has no detectable magic signature."""
        empty = self.dir_path / "empty.bin"
        empty.write_bytes(b"")
        self.assertIsNone(HeaderValidator.detect_extension(empty))

    def test_detect_extension_unknown_magic_returns_none(self) -> None:
        """Plain text content matches no known magic signature."""
        plain = self.dir_path / "notes.txt"
        plain.write_text("just words", encoding="utf-8")
        self.assertIsNone(HeaderValidator.detect_extension(plain))

    def test_validate_extension_accepts_missing_dot(self) -> None:
        """Target extensions may be passed without the leading dot."""
        png_file = self.dir_path / "img.dat"
        png_file.write_bytes(PNG_HEADER)
        self.assertTrue(HeaderValidator.validate_extension(png_file, "png"))

    def test_validate_extension_unknown_ext_assumed_valid(self) -> None:
        """Extensions without a known signature are treated as valid."""
        data = self.dir_path / "blob.xyz"
        data.write_bytes(b"whatever bytes")
        self.assertTrue(HeaderValidator.validate_extension(data, ".xyz"))


class TestChangeExtensionEdgeCases(unittest.TestCase):
    """Guard clauses and error paths of FileExtensionChanger."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = pathlib.Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _changer(self, **kwargs: bool) -> FileExtensionChanger:
        """Build a changer with sensible defaults for these tests."""
        return FileExtensionChanger(**kwargs)

    def test_missing_file_returns_failure(self) -> None:
        """A nonexistent source path reports failure and a message."""
        changer = self._changer()
        success, msg = changer.change_extension(self.dir_path / "nope.dat", ".png")
        self.assertFalse(success)
        self.assertIn("File not found", msg)

    def test_target_without_dot_is_normalized(self) -> None:
        """A target extension given as 'txt' behaves like '.txt'."""
        src = self.dir_path / "doc.dat"
        src.write_text("hello", encoding="utf-8")

        success, msg = self._changer().change_extension(src, "txt")
        self.assertTrue(success)
        self.assertTrue((self.dir_path / "doc.txt").exists())
        self.assertIn("Renamed doc.dat -> doc.txt", msg)

    def test_same_extension_short_circuits(self) -> None:
        """Files already carrying the target extension are left alone."""
        src = self.dir_path / "already.png"
        src.write_bytes(PNG_HEADER)

        success, msg = self._changer().change_extension(src, ".png")
        self.assertTrue(success)
        self.assertIn("already has target extension .png", msg)
        self.assertTrue(src.exists())

    def test_existing_target_blocks_rename(self) -> None:
        """Renames that would clobber an existing file are rejected."""
        existing = self.dir_path / "taken.png"
        existing.write_bytes(PNG_HEADER)
        src = self.dir_path / "taken.dat"
        src.write_bytes(PNG_HEADER)

        success, msg = self._changer().change_extension(src, ".png")
        self.assertFalse(success)
        self.assertIn(f"Target path already exists: {existing}", msg)
        self.assertTrue(src.exists())

    def test_rename_oserror_reports_failure(self) -> None:
        """OSError during rename is converted into a failure message."""
        src = self.dir_path / "busy.dat"
        src.write_bytes(PNG_HEADER)
        changer = self._changer(force=True)

        with patch.object(pathlib.Path, "rename", side_effect=OSError("file in use")):
            success, msg = changer.change_extension(src, ".png")
        self.assertFalse(success)
        self.assertIn("Error renaming", msg)


class TestBatchProcess(unittest.TestCase):
    """Directory-wide batch behaviour."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = pathlib.Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_invalid_directory_returns_zero_stats(self) -> None:
        """A nonexistent directory yields all-zero statistics."""
        stats = FileExtensionChanger().batch_process(self.dir_path / "missing", ".png")
        self.assertEqual(stats, {"success": 0, "skipped": 0, "failed": 0})

    def test_batch_counts_success_and_skips(self) -> None:
        """Valid files rename while mismatched ones count as skipped."""
        good = self.dir_path / "good.dat"
        good.write_bytes(PNG_HEADER)
        bad = self.dir_path / "bad.dat"
        bad.write_text("plain", encoding="utf-8")

        stats = FileExtensionChanger().batch_process(self.dir_path, ".png")
        self.assertEqual(stats["success"], 1)
        self.assertEqual(stats["skipped"], 1)
        self.assertTrue((self.dir_path / "good.png").exists())
        self.assertTrue(bad.exists())


class TestMainCLI(unittest.TestCase):
    """End-to-end CLI tests."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = pathlib.Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_main_single_file_success_exit_zero(self) -> None:
        """Renaming one valid file exits 0 and prints the outcome."""
        src = self.dir_path / "pic.dat"
        src.write_bytes(PNG_HEADER)

        code = main([str(src), "-e", ".png"])
        self.assertEqual(code, 0)
        self.assertTrue((self.dir_path / "pic.png").exists())

    def test_main_single_file_mismatch_exits_one(self) -> None:
        """A validation mismatch on one file exits 1."""
        src = self.dir_path / "text.txt"
        src.write_text("words", encoding="utf-8")

        code = main([str(src), "-e", ".png"])
        self.assertEqual(code, 1)
        self.assertTrue(src.exists())

    def test_main_directory_mode_exits_zero(self) -> None:
        """Directory mode batches files and always exits 0."""
        (self.dir_path / "a.dat").write_bytes(PNG_HEADER)

        code = main([str(self.dir_path), "-e", ".png", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertTrue((self.dir_path / "a.dat").exists())

    def test_main_nonexistent_path_exits_one(self) -> None:
        """Unknown paths report an error and exit 1."""
        code = main([str(self.dir_path / "ghost"), "-e", ".png"])
        self.assertEqual(code, 1)

    def test_build_parser_defaults_and_flags(self) -> None:
        """Parser exposes pattern/dry-run/force options with defaults."""
        parser = build_parser()
        parsed = parser.parse_args(["some/path", "-e", "jpg"])
        self.assertEqual(parsed.path, pathlib.Path("some/path"))
        self.assertEqual(parsed.extension, "jpg")
        self.assertEqual(parsed.pattern, "*")
        self.assertFalse(parsed.dry_run)
        self.assertFalse(parsed.force)

    def test_force_flag_is_plumbed_through(self) -> None:
        """--force lets mismatched headers be renamed anyway."""
        src = self.dir_path / "mismatch.dat"
        src.write_text("words", encoding="utf-8")

        code = main([str(src), "-e", ".png", "--force"])
        self.assertEqual(code, 0)
        self.assertTrue((self.dir_path / "mismatch.png").exists())


if __name__ == "__main__":
    unittest.main()
