import pathlib
import tempfile
import unittest
import zipfile

from main import RecursiveArchiveExtractor


class TestRecursiveArchiveExtractor(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = pathlib.Path(self.temp_dir.name)
        self.out_dir = self.work_dir / "output"

        # Create inner zip archive
        self.inner_zip_path = self.work_dir / "inner.zip"
        with zipfile.ZipFile(self.inner_zip_path, "w") as zf:
            zf.writestr("inner_file.txt", "Content of inner file")

        # Create outer zip archive containing inner zip
        self.outer_zip_path = self.work_dir / "outer.zip"
        with zipfile.ZipFile(self.outer_zip_path, "w") as zf:
            zf.writestr("outer_file.txt", "Content of outer file")
            with open(self.inner_zip_path, "rb") as inner_f:
                zf.writestr("nested/inner.zip", inner_f.read())

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_recursive_extraction(self):
        extractor = RecursiveArchiveExtractor(
            output_dir=self.out_dir, max_depth=3, max_size_mb=10, max_files=100
        )
        metrics = extractor.process_recursive(self.outer_zip_path)

        self.assertGreaterEqual(metrics.total_files, 2)
        self.assertEqual(len(metrics.errors), 0)

        # Check extracted files exist
        extracted_inner = list(self.out_dir.rglob("inner_file.txt"))
        self.assertTrue(len(extracted_inner) > 0)

    def test_password_protected_zip(self):
        encrypted_zip_path = self.work_dir / "encrypted.zip"
        password = "secret_pass_123"

        with zipfile.ZipFile(encrypted_zip_path, "w") as zf:
            zf.setpassword(password.encode("utf-8"))
            zf.writestr(
                "secret.txt",
                b"Secret contents requiring decryption",
                compress_type=zipfile.ZIP_DEFLATED,
            )

        extractor = RecursiveArchiveExtractor(
            output_dir=self.out_dir, passwords=["wrong1", password, "wrong2"]
        )
        metrics = extractor.process_recursive(encrypted_zip_path)
        self.assertEqual(len(metrics.errors), 0)

        extracted_secret = list(self.out_dir.rglob("secret.txt"))
        self.assertTrue(len(extracted_secret) > 0)

    def test_archive_bomb_limit_file_count(self):
        # Limit max_files to 1 file
        extractor = RecursiveArchiveExtractor(
            output_dir=self.out_dir, max_depth=3, max_files=1
        )
        metrics = extractor.process_recursive(self.outer_zip_path)
        # Should record bomb exception in errors list
        self.assertTrue(any("Exceeded max file count" in err for err in metrics.errors))

    def test_safe_path_traversal(self):
        target_dir = self.work_dir / "target"
        unsafe_path = target_dir / ".." / "outside.txt"
        safe_path = target_dir / "sub" / "inside.txt"

        self.assertFalse(
            RecursiveArchiveExtractor.is_safe_path(target_dir, unsafe_path)
        )
        self.assertTrue(RecursiveArchiveExtractor.is_safe_path(target_dir, safe_path))


if __name__ == "__main__":
    unittest.main()
