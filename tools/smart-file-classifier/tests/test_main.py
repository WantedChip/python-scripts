import json
import pathlib
import tempfile
import unittest

from main import BinaryHeaderMatcher, FileClassifier, main


class TestSmartFileClassifier(unittest.TestCase):

    def setUp(self):
        self.temp_src = tempfile.TemporaryDirectory()
        self.temp_out = tempfile.TemporaryDirectory()

        self.src_dir = pathlib.Path(self.temp_src.name)
        self.out_dir = pathlib.Path(self.temp_out.name)

        # Create mislabeled PNG file (named sample.txt)
        self.fake_txt = self.src_dir / "sample.txt"
        self.fake_txt.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

        # Create valid PDF file
        self.valid_pdf = self.src_dir / "document.pdf"
        self.valid_pdf.write_bytes(b"%PDF-1.4 header content")

        # Create valid ZIP file
        self.valid_zip = self.src_dir / "archive.zip"
        self.valid_zip.write_bytes(b"PK\x03\x04\x14\x00\x00\x00")

    def tearDown(self):
        self.temp_src.cleanup()
        self.temp_out.cleanup()

    def test_binary_header_matching(self):
        category, ext = BinaryHeaderMatcher.classify_file(self.fake_txt)
        self.assertEqual(category, "images")
        self.assertEqual(ext, ".png")

        category_pdf, ext_pdf = BinaryHeaderMatcher.classify_file(self.valid_pdf)
        self.assertEqual(category_pdf, "documents")
        self.assertEqual(ext_pdf, ".pdf")

    def test_classification_and_copy(self):
        classifier = FileClassifier(
            target_dir=self.out_dir, mode="copy", fix_extensions=True, dry_run=False
        )
        rec = classifier.process_file(self.fake_txt)

        self.assertEqual(rec.detected_category, "images")
        self.assertTrue(rec.extension_corrected)

        # Corrected filename should be sample.png in out_dir/images
        expected_dest = self.out_dir / "images" / "sample.png"
        self.assertTrue(expected_dest.exists())
        self.assertTrue(self.fake_txt.exists())  # Copy mode leaves source file

    def test_main_cli_execution_with_log(self):
        log_file = self.out_dir / "log.json"
        exit_code = main(
            [
                str(self.src_dir),
                str(self.out_dir),
                "--mode",
                "copy",
                "--log-file",
                str(log_file),
            ]
        )
        self.assertEqual(exit_code, 0)
        self.assertTrue(log_file.exists())

        with open(log_file, "r", encoding="utf-8") as f:
            logs = json.load(f)
            self.assertGreaterEqual(len(logs), 3)


if __name__ == "__main__":
    unittest.main()
