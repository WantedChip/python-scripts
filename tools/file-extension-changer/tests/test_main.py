import pathlib
import tempfile
import unittest

from main import FileExtensionChanger, HeaderValidator


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


if __name__ == "__main__":
    unittest.main()
