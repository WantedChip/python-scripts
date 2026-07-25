import tempfile
import unittest
from pathlib import Path

from main import bulk_convert_encoding, convert_file_encoding, detect_encoding


class TestTextEncodingConverter(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.input_file = Path(self.temp_dir.name) / "input.txt"
        self.output_file = Path(self.temp_dir.name) / "output.txt"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_detect_encoding_utf8_bom(self):
        content = b"\xef\xbb\xbfHello World"
        self.assertEqual(detect_encoding(content), "utf-8-sig")

    def test_detect_encoding_ascii(self):
        content = b"Simple ASCII text"
        self.assertEqual(detect_encoding(content), "ascii")

    def test_detect_encoding_utf8(self):
        content = "Café y Té".encode("utf-8")
        self.assertEqual(detect_encoding(content), "utf-8")

    def test_convert_file_latin1_to_utf8(self):
        text = "München Crème Brûlée"
        latin1_bytes = text.encode("latin-1")
        with open(self.input_file, "wb") as f:
            f.write(latin1_bytes)

        detected, written = convert_file_encoding(
            input_path=self.input_file,
            output_path=self.output_file,
            target_encoding="utf-8",
        )

        with open(self.output_file, "r", encoding="utf-8") as f:
            read_text = f.read()

        self.assertEqual(read_text, text)

    def test_convert_file_utf16_to_utf8(self):
        text = "Hello World with UTF-16 encoding 🚀"
        utf16_bytes = text.encode("utf-16")
        with open(self.input_file, "wb") as f:
            f.write(utf16_bytes)

        detected, written = convert_file_encoding(
            input_path=self.input_file,
            output_path=self.output_file,
            target_encoding="utf-8",
        )

        with open(self.output_file, "r", encoding="utf-8") as f:
            read_text = f.read()

        self.assertEqual(read_text, text)

    def test_bulk_convert(self):
        in_dir = Path(self.temp_dir.name) / "src"
        out_dir = Path(self.temp_dir.name) / "dst"
        in_dir.mkdir()

        (in_dir / "file1.txt").write_bytes("Sample 1".encode("latin-1"))
        (in_dir / "file2.txt").write_bytes("Sample 2".encode("utf-8"))

        results = bulk_convert_encoding(
            input_dir=in_dir,
            output_dir=out_dir,
            pattern="*.txt",
            target_encoding="utf-8",
        )

        self.assertEqual(len(results), 2)
        self.assertTrue((out_dir / "file1.txt").exists())
        self.assertTrue((out_dir / "file2.txt").exists())


if __name__ == "__main__":
    unittest.main()
