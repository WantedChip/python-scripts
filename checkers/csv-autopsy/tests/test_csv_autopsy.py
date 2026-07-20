import io
import os
import sys
import unittest
from unittest.mock import patch

# Ensure csv_autopsy is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import csv_autopsy  # noqa: E402


# In-memory Mock File class
class MockFile:
    def __init__(self, content: bytes, encoding=None, errors=None, mode="r"):
        self.mode = mode
        self.encoding = encoding or "utf-8"
        self.errors = errors
        self.content = content
        if "b" in mode:
            self.stream = io.BytesIO(content)
        else:
            # Try decoding. If it fails, raise UnicodeDecodeError
            # to match real file open/read behavior.
            try:
                text = content.decode(self.encoding, errors=self.errors or "strict")
            except UnicodeDecodeError as e:
                raise e
            self.stream = io.StringIO(text)

    def read(self, size=-1):
        return self.stream.read(size)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def __iter__(self):
        return iter(self.stream)

    def __next__(self):
        return next(self.stream)


class TestCsvAutopsy(unittest.TestCase):

    def setUp(self):
        self.content_dict = {}

        def open_side_effect(file_path, mode="r", encoding=None, errors=None):
            if file_path not in self.content_dict:
                raise FileNotFoundError(f"No mock content for {file_path}")
            content = self.content_dict[file_path]
            return MockFile(content, encoding=encoding, errors=errors, mode=mode)

        self.open_patcher = patch("builtins.open", side_effect=open_side_effect)
        self.open_patcher.start()

    def tearDown(self):
        self.open_patcher.stop()

    def test_sniff_encoding_details_utf8_bom(self):
        self.content_dict["test.csv"] = b"\xef\xbb\xbfcol1,col2\n"
        enc, issues = csv_autopsy.sniff_encoding_details("test.csv")
        self.assertEqual(enc, "utf-8-sig")
        self.assertTrue(any("UTF-8 BOM signature" in issue for issue in issues))

    def test_sniff_encoding_details_utf16_bom(self):
        self.content_dict["test.csv"] = b"\xff\xfe" + "col1,col2\n".encode("utf-16-le")
        enc, issues = csv_autopsy.sniff_encoding_details("test.csv")
        self.assertEqual(enc, "utf-16")
        self.assertTrue(any("UTF-16 BOM signature" in issue for issue in issues))

    def test_sniff_encoding_details_clean_utf8(self):
        self.content_dict["test.csv"] = b"col1,col2\nval1,val2\n"
        enc, issues = csv_autopsy.sniff_encoding_details("test.csv")
        # In this tool, clean UTF-8 falls under utf-8-sig because it's first in list
        # and has no BOM enforcement on standard read.
        self.assertEqual(enc, "utf-8-sig")

    def test_sniff_encoding_details_invalid_utf8(self):
        # We want to force all text encodings to fail to trigger fallback branch.
        self.content_dict["test.csv"] = b"col1,col2\nval1,\x81val2\n"

        # We temporarily patch MockFile to raise UnicodeDecodeError for text encodings
        original_init = MockFile.__init__

        def custom_init(slf, content, encoding=None, errors=None, mode="r"):
            if "b" not in mode:
                # Force UnicodeDecodeError
                raise UnicodeDecodeError("mock_codec", b"", 0, 1, "forced test failure")
            else:
                # Standard binary open
                original_init(slf, content, encoding, errors, mode)

        with patch.object(MockFile, "__init__", custom_init):
            enc, issues = csv_autopsy.sniff_encoding_details("test.csv")

        self.assertEqual(enc, "latin-1")
        self.assertTrue(
            any("Mixed encodings or corrupted binary data" in issue for issue in issues)
        )
        self.assertTrue(any("Invalid UTF-8 bytes found" in issue for issue in issues))

    def test_scan_csv_structure_empty(self):
        self.content_dict["test.csv"] = b""
        issues, metrics = csv_autopsy.scan_csv_structure("test.csv", "utf-8")
        self.assertTrue(any("CSV file is empty" in issue for issue in issues))
        self.assertEqual(metrics, {})

    def test_scan_csv_structure_delimiter(self):
        self.content_dict["test.csv"] = b"col1;col2\nval1;val2\n"
        issues, metrics = csv_autopsy.scan_csv_structure("test.csv", "utf-8")
        self.assertEqual(metrics["delimiter"], ";")
        self.assertEqual(metrics["rows_processed"], 2)

    def test_scan_csv_structure_control_chars(self):
        # Contains null byte, zero width space, and Ctrl+A (\x01)
        self.content_dict["test.csv"] = "col1,col2\nval1\x00,\u200bval2\x01\n".encode(
            "utf-8"
        )
        issues, metrics = csv_autopsy.scan_csv_structure("test.csv", "utf-8")
        self.assertTrue(any("Null byte character" in issue for issue in issues))
        self.assertTrue(any("Zero-width space character" in issue for issue in issues))
        self.assertTrue(
            any("Invisible control character (ASCII 1)" in issue for issue in issues)
        )

    def test_scan_csv_structure_quoting_errors(self):
        # Quoting errors: double quote in middle of unquoted field, closed quote error
        self.content_dict["test.csv"] = (
            b'col1,col2\nval1"invalid,val2\n"val1"invalid,val2\n'
        )
        issues, metrics = csv_autopsy.scan_csv_structure("test.csv", "utf-8")
        self.assertTrue(
            any(
                "Double quote found in middle of unquoted field." in issue
                for issue in issues
            )
        )
        self.assertTrue(
            any(
                "Double quote closed but not followed by delimiter." in issue
                for issue in issues
            )
        )

    def test_scan_csv_structure_unclosed_quotes(self):
        self.content_dict["test.csv"] = b'col1,col2\n"val1,val2\n'
        issues, metrics = csv_autopsy.scan_csv_structure("test.csv", "utf-8")
        self.assertTrue(
            any(
                "Unclosed double-quotes detected at the end of the file." in issue
                for issue in issues
            )
        )

    def test_scan_csv_structure_duplicate_headers(self):
        self.content_dict["test.csv"] = b"id,name,name\n1,a,b\n"
        issues, _ = csv_autopsy.scan_csv_structure("test.csv", "utf-8")
        self.assertTrue(
            any("Duplicate columns names found: name" in issue for issue in issues)
        )

    def test_scan_csv_structure_inconsistent_cols(self):
        self.content_dict["test.csv"] = b"col1,col2\n1,2\n1,2,3\n"
        issues, _ = csv_autopsy.scan_csv_structure("test.csv", "utf-8")
        self.assertTrue(
            any(
                "Inconsistent column count. Expected 2 fields but got 3" in issue
                for issue in issues
            )
        )

    def test_scan_csv_structure_date_checks(self):
        # Sniffs "date" in header, check multiple formats and invalid format
        self.content_dict["test.csv"] = b"my_date\n2026-07-19\n07/19/2026\nnot-a-date\n"
        issues, _ = csv_autopsy.scan_csv_structure("test.csv", "utf-8")
        self.assertTrue(
            any(
                "Inconsistent date formats. Multiple formats detected" in issue
                for issue in issues
            )
        )
        self.assertTrue(
            any("fields could not be parsed as date" in issue for issue in issues)
        )

    def test_scan_csv_structure_numeric_checks(self):
        # Sniffs "price" in header, detects non-numeric
        self.content_dict["test.csv"] = b"price\n$10.50\n100\ninvalid_val\n"
        issues, _ = csv_autopsy.scan_csv_structure("test.csv", "utf-8")
        self.assertTrue(
            any(
                "Non-numeric values found in expected numeric column" in issue
                for issue in issues
            )
        )

    @patch("sys.argv", ["csv_autopsy.py", "test.csv"])
    @patch("sys.exit")
    def test_main_pass(self, mock_exit):
        self.content_dict["test.csv"] = b"col1,col2\n1,2\n"
        mock_exit.side_effect = SystemExit(0)

        with self.assertRaises(SystemExit) as cm:
            csv_autopsy.main()
        self.assertEqual(cm.exception.code, 0)

    @patch("sys.argv", ["csv_autopsy.py", "test.csv"])
    @patch("sys.exit")
    def test_main_fail(self, mock_exit):
        # Duplicate columns -> Error -> exit(1)
        self.content_dict["test.csv"] = b"col1,col1\n1,2\n"
        mock_exit.side_effect = SystemExit(1)

        with self.assertRaises(SystemExit) as cm:
            csv_autopsy.main()
        self.assertEqual(cm.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
