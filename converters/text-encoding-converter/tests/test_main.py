import codecs
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from main import (
    build_parser,
    bulk_convert_encoding,
    convert_file_encoding,
    detect_encoding,
    main,
)


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


class TestDetectEncodingAdvanced(unittest.TestCase):
    """BOM, heuristic and fallback branches of detect_encoding."""

    def test_empty_data_defaults_to_utf8(self) -> None:
        """Empty byte strings are reported as utf-8."""
        self.assertEqual(detect_encoding(b""), "utf-8")

    def test_utf32_le_bom_detected(self) -> None:
        """UTF-32 LE BOMs are recognized."""
        self.assertEqual(
            detect_encoding(codecs.BOM_UTF32_LE + b"a\x00\x00\x00"), "utf-32-le"
        )

    def test_utf32_be_bom_detected(self) -> None:
        """UTF-32 BE BOMs are recognized."""
        self.assertEqual(
            detect_encoding(codecs.BOM_UTF32_BE + b"\x00\x00\x00a"), "utf-32-be"
        )

    def test_utf16_be_bom_detected(self) -> None:
        """UTF-16 BE BOMs are recognized."""
        self.assertEqual(detect_encoding(codecs.BOM_UTF16_BE + b"\x00a"), "utf-16-be")

    def test_bomless_utf16_le_via_nul_heuristic(self) -> None:
        """NUL-containing non-UTF-8 bytes decode as UTF-16."""
        data = "éhi".encode("utf-16-le")
        self.assertEqual(detect_encoding(data), "utf-16")

    def test_odd_length_nul_bytes_fall_through_utf16(self) -> None:
        """Odd-length NUL data fails the UTF-16 guess and moves on."""
        data = b"\xe9\x00x"
        self.assertEqual(detect_encoding(data), "windows-1252")

    def test_windows_1252_smart_quotes(self) -> None:
        """CP1252-only bytes such as smart quotes are identified."""
        self.assertEqual(detect_encoding(b"say \x93hi\x94 ok"), "windows-1252")

    def test_latin1_final_fallback(self) -> None:
        """Bytes invalid in CP1252 fall back to latin-1."""
        self.assertEqual(detect_encoding(b"\x81\x95 data"), "latin-1")


class TestConvertFileEncodingOptions(unittest.TestCase):
    """Explicit source encoding and BOM handling of conversion."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.input_file = self.dir_path / "input.txt"
        self.output_file = self.dir_path / "output.txt"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_explicit_source_encoding_skips_detection(self) -> None:
        """source_encoding overrides automatic detection."""
        text = "Über café"
        self.input_file.write_text(text, encoding="cp1252")

        detected, _ = convert_file_encoding(
            input_path=self.input_file,
            output_path=self.output_file,
            source_encoding="cp1252",
        )

        self.assertEqual(detected, "cp1252")
        self.assertEqual(
            self.output_file.read_text(encoding="utf-8"),
            text,
        )

    def test_utf16_le_bom_stripped_from_output(self) -> None:
        """Byte-order codecs have their retained BOM removed."""
        text = "BOM removal check"
        self.input_file.write_bytes(codecs.BOM_UTF16_LE + text.encode("utf-16-le"))

        detected, written = convert_file_encoding(
            input_path=self.input_file,
            output_path=self.output_file,
            target_encoding="utf-8",
        )

        self.assertEqual(detected, "utf-16-le")
        result = self.output_file.read_text(encoding="utf-8")
        self.assertNotIn("\ufeff", result)
        self.assertEqual(result, text)
        self.assertGreater(written, 0)

    def test_output_parent_directory_created(self) -> None:
        """Missing output parent directories are created on demand."""
        self.input_file.write_text("nested output target", encoding="utf-8")
        target = self.dir_path / "sub" / "dir" / "out.txt"
        _, _ = convert_file_encoding(
            input_path=self.input_file,
            output_path=target,
        )
        self.assertTrue(target.exists())


class TestTextEncodingConverterCli(unittest.TestCase):
    """CLI-level tests for build_parser and main()."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_build_parser_defaults(self) -> None:
        """Defaults: utf-8 target, replace errors, single-file mode."""
        parser = build_parser()
        args = parser.parse_args(["a.txt", "b.txt"])
        self.assertEqual(args.target, "utf-8")
        self.assertIsNone(args.source)
        self.assertEqual(args.errors, "replace")
        self.assertFalse(args.bulk)
        self.assertEqual(args.pattern, "*")

    def test_main_single_file_conversion(self) -> None:
        """Single-file mode converts and prints a summary line."""
        src = self.dir_path / "story.txt"
        dst = self.dir_path / "story.utf16.txt"
        src.write_text("Encode me", encoding="utf-8")

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main([str(src), str(dst), "--target", "utf-16"])

        self.assertEqual(exit_code, 0)
        self.assertIn("Converted", stdout.getvalue())
        self.assertEqual(dst.read_bytes().decode("utf-16"), "Encode me")

    def test_main_bulk_mode_preserves_relative_paths(self) -> None:
        """Bulk mode walks subfolders and mirrors the directory tree."""
        in_dir = self.dir_path / "src"
        out_dir = self.dir_path / "dst"
        (in_dir / "nested").mkdir(parents=True)
        (in_dir / "a.txt").write_bytes("alpha".encode("utf-8"))
        (in_dir / "nested" / "b.txt").write_bytes("beta".encode("latin-1"))

        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(
                [
                    str(in_dir),
                    str(out_dir),
                    "--bulk",
                    "--pattern",
                    "*.txt",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("Converted 2 files", stdout.getvalue())
        self.assertTrue((out_dir / "nested" / "b.txt").exists())

    def test_main_missing_input_returns_error(self) -> None:
        """A nonexistent input exits 1 with an error message."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = main(
                [str(self.dir_path / "ghost.txt"), str(self.dir_path / "out.txt")]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("Error:", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
