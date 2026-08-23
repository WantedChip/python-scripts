"""Unit tests for Book Info Scraper."""

import contextlib
import io
import json
import os
import tempfile
import unittest
import urllib.error
from typing import Any
from unittest.mock import MagicMock, patch

from main import (
    BookMetadata,
    build_parser,
    clean_isbn,
    fetch_open_library_data,
    format_markdown,
    format_terminal_card,
    main,
    parse_book_metadata,
    validate_isbn,
    validate_isbn_10,
    validate_isbn_13,
)


def _urlopen_result(payload: Any, status: int = 200) -> MagicMock:
    """Build a mock urlopen return value usable as a context manager."""
    resp = MagicMock()
    resp.status = status
    body = payload if isinstance(payload, str) else json.dumps(payload)
    resp.read.return_value = body.encode("utf-8")
    resp.__enter__.return_value = resp
    return resp


class TestBookInfoScraper(unittest.TestCase):
    """Test suite for ISBN validation and metadata parsing."""

    def test_clean_isbn(self) -> None:
        self.assertEqual(clean_isbn(" 978-0-135957-05-9 "), "9780135957059")
        self.assertEqual(clean_isbn("0-321-57351-x"), "032157351X")

    def test_validate_isbn_10(self) -> None:
        self.assertTrue(validate_isbn_10("032157351X"))
        self.assertTrue(validate_isbn_10("0135957052"))
        self.assertFalse(validate_isbn_10("0321573510"))
        self.assertFalse(validate_isbn_10("12345"))

    def test_validate_isbn_13(self) -> None:
        self.assertTrue(validate_isbn_13("9780135957059"))
        self.assertTrue(validate_isbn_13("9780321573513"))
        self.assertFalse(validate_isbn_13("9780135957050"))
        self.assertFalse(validate_isbn_13("978013595705"))

    def test_validate_isbn_wrapper(self) -> None:
        is_valid, isbn_type, cleaned = validate_isbn("978-0-135957-05-9")
        self.assertTrue(is_valid)
        self.assertEqual(isbn_type, "ISBN-13")
        self.assertEqual(cleaned, "9780135957059")

        is_valid, isbn_type, cleaned = validate_isbn("0-321-57351-X")
        self.assertTrue(is_valid)
        self.assertEqual(isbn_type, "ISBN-10")
        self.assertEqual(cleaned, "032157351X")

        is_valid, isbn_type, _ = validate_isbn("invalid-isbn")
        self.assertFalse(is_valid)
        self.assertEqual(isbn_type, "UNKNOWN")

    def test_parse_book_metadata(self) -> None:
        raw_api_data = {
            "title": "The Pragmatic Programmer",
            "authors": [{"name": "Andrew Hunt"}, {"name": "David Thomas"}],
            "publishers": [{"name": "Addison-Wesley"}],
            "publish_date": "1999",
            "number_of_pages": 352,
            "subjects": [
                {"name": "Computer programming"},
                {"name": "Software engineering"},
            ],
            "cover": {"medium": "https://covers.openlibrary.org/b/id/123-M.jpg"},
            "url": "https://openlibrary.org/books/OL123M",
        }

        metadata = parse_book_metadata("9780201616224", "ISBN-13", raw_api_data)
        self.assertEqual(metadata.title, "The Pragmatic Programmer")
        self.assertEqual(metadata.authors, ["Andrew Hunt", "David Thomas"])
        self.assertEqual(metadata.publish_date, "1999")
        self.assertEqual(metadata.number_of_pages, 352)
        self.assertIn("Computer programming", metadata.subjects)
        self.assertEqual(
            metadata.cover_url, "https://covers.openlibrary.org/b/id/123-M.jpg"
        )

    def test_format_terminal_card(self) -> None:
        book = BookMetadata(
            isbn="9780135957059",
            isbn_type="ISBN-13",
            title="Clean Code",
            authors=["Robert C. Martin"],
            publish_date="2008",
            publishers=["Prentice Hall"],
            number_of_pages=464,
            subjects=["Refactoring"],
            cover_url=None,
            openlibrary_url=None,
        )
        card = format_terminal_card(book)
        self.assertIn("Clean Code", card)
        self.assertIn("Robert C. Martin", card)
        self.assertIn("ISBN-13: 9780135957059", card)

    def test_format_markdown(self) -> None:
        book = BookMetadata(
            isbn="032157351X",
            isbn_type="ISBN-10",
            title="Refactoring",
            authors=["Martin Fowler"],
            publish_date="1999",
            publishers=["Addison-Wesley"],
            number_of_pages=432,
            subjects=["Design Patterns"],
            cover_url="https://example.com/cover.jpg",
            openlibrary_url="https://example.com/book",
        )
        md = format_markdown(book)
        self.assertIn("# Refactoring", md)
        self.assertIn("**Author(s):** Martin Fowler", md)
        self.assertIn("![Book Cover](https://example.com/cover.jpg)", md)


class TestIsbnValidationEdges(unittest.TestCase):
    """Edge cases of the ISBN check-digit validators."""

    def test_validate_isbn_10_rejects_invalid_characters(self) -> None:
        self.assertFalse(validate_isbn_10("032157351!"))
        self.assertFalse(validate_isbn_10("032X57351X"))

    def test_validate_isbn_13_rejects_non_digit_input(self) -> None:
        self.assertFalse(validate_isbn_13("978013595705X"))
        self.assertFalse(validate_isbn_13("978-0-13"))

    def test_book_metadata_to_dict_round_trip(self) -> None:
        book = BookMetadata(
            isbn="9780135957059",
            isbn_type="ISBN-13",
            title="Clean Code",
            authors=["Robert C. Martin"],
            publish_date="2008",
            publishers=["Prentice Hall"],
            number_of_pages=464,
            subjects=["Refactoring"],
            cover_url=None,
            openlibrary_url=None,
        )
        as_dict = book.to_dict()
        self.assertEqual(as_dict["isbn"], "9780135957059")
        self.assertEqual(as_dict["authors"], ["Robert C. Martin"])
        self.assertEqual(set(as_dict.keys()), set(book.__dataclass_fields__.keys()))


class TestFetchOpenLibrary(unittest.TestCase):
    """HTTP layer of fetch_open_library_data with mocked urlopen."""

    def test_fetch_success_returns_bib_key_payload(self) -> None:
        payload = {"ISBN:9780135957059": {"title": "Clean Code"}}
        with patch(
            "main.urllib.request.urlopen", return_value=_urlopen_result(payload)
        ) as mock_open:
            data = fetch_open_library_data("9780135957059")
        self.assertIsNotNone(data)
        assert data is not None
        self.assertEqual(data["title"], "Clean Code")
        url = mock_open.call_args.args[0].full_url
        self.assertIn("bibkeys=ISBN:9780135957059", url)
        self.assertIn("jscmd=data", url)

    def test_fetch_response_missing_bib_key_returns_none(self) -> None:
        with patch(
            "main.urllib.request.urlopen",
            return_value=_urlopen_result({"ISBN:other": {}}),
        ):
            self.assertIsNone(fetch_open_library_data("9780135957059"))

    def test_fetch_non_200_status_returns_none(self) -> None:
        resp = _urlopen_result({}, status=503)
        with patch("main.urllib.request.urlopen", return_value=resp):
            self.assertIsNone(fetch_open_library_data("9780135957059"))

    def test_fetch_network_error_returns_none(self) -> None:
        with patch(
            "main.urllib.request.urlopen",
            side_effect=urllib.error.URLError("offline"),
        ):
            self.assertIsNone(fetch_open_library_data("9780135957059"))

    def test_fetch_malformed_json_returns_none(self) -> None:
        resp = _urlopen_result("<html>not json</html>")
        with patch("main.urllib.request.urlopen", return_value=resp):
            self.assertIsNone(fetch_open_library_data("9780135957059"))


class TestParseBookMetadataFallbacks(unittest.TestCase):
    """Parsing fallbacks for sparse or unusually shaped API payloads."""

    def test_missing_authors_fall_back_to_unknown(self) -> None:
        metadata = parse_book_metadata("032157351X", "ISBN-10", {"title": "T"})
        self.assertEqual(metadata.authors, ["Unknown Author"])

    def test_string_publishers_and_subjects_are_accepted(self) -> None:
        raw = {
            "title": "Mixed Shapes",
            "publishers": ["Plain String Press"],
            "subjects": ["Mathematics", {"name": "Physics"}],
        }
        metadata = parse_book_metadata("9780135957059", "ISBN-13", raw)
        self.assertEqual(metadata.publishers, ["Plain String Press"])
        self.assertEqual(metadata.subjects, ["Mathematics", "Physics"])

    def test_cover_url_prefers_large_then_medium_then_small(self) -> None:
        raw = {
            "cover": {
                "small": "https://covers.example.com/s.jpg",
                "medium": "https://covers.example.com/m.jpg",
                "large": "https://covers.example.com/l.jpg",
            }
        }
        metadata = parse_book_metadata("9780135957059", "ISBN-13", raw)
        self.assertEqual(metadata.cover_url, "https://covers.example.com/l.jpg")

        del raw["cover"]["large"]
        self.assertEqual(
            parse_book_metadata("9780135957059", "ISBN-13", raw).cover_url,
            "https://covers.example.com/m.jpg",
        )
        del raw["cover"]["medium"]
        self.assertEqual(
            parse_book_metadata("9780135957059", "ISBN-13", raw).cover_url,
            "https://covers.example.com/s.jpg",
        )

    def test_defaults_applied_for_empty_payload(self) -> None:
        metadata = parse_book_metadata("9780135957059", "ISBN-13", {})
        self.assertEqual(metadata.title, "Unknown Title")
        self.assertEqual(metadata.publish_date, "Unknown Date")
        self.assertIsNone(metadata.cover_url)
        self.assertIsNone(metadata.openlibrary_url)

    def test_markdown_without_subjects_or_links_uses_na(self) -> None:
        book = BookMetadata(
            isbn="032157351X",
            isbn_type="ISBN-10",
            title="Bare Book",
            authors=["Ann Author"],
            publish_date="2001",
            publishers=[],
            number_of_pages=None,
            subjects=[],
            cover_url=None,
            openlibrary_url=None,
        )
        md = format_markdown(book)
        self.assertIn("**Publisher:** N/A", md)
        self.assertIn("**Pages:** N/A", md)
        self.assertIn("## Subjects\nN/A", md)
        self.assertNotIn("![Book Cover]", md)
        self.assertNotIn("[Open Library Profile]", md)


class TestBookInfoCli(unittest.TestCase):
    """CLI-level tests for build_parser and main()."""

    def test_build_parser_defaults(self) -> None:
        args = build_parser().parse_args(["9780135957059"])
        self.assertEqual(args.isbn, "9780135957059")
        self.assertEqual(args.format, "terminal")
        self.assertIsNone(args.output)

    def _run_main(self, argv: list) -> tuple:
        """Run main() capturing stdout/stderr; return (code, out, err)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_main_rejects_invalid_isbn(self) -> None:
        code, _, err = self._run_main(["not-an-isbn"])
        self.assertEqual(code, 1)
        self.assertIn("not a valid ISBN-10 or ISBN-13", err)

    def test_main_reports_missing_metadata(self) -> None:
        with patch("main.fetch_open_library_data", return_value=None):
            code, _, err = self._run_main(["9780135957059"])
        self.assertEqual(code, 1)
        self.assertIn("No metadata found on Open Library", err)

    SAMPLE_RAW = {
        "title": "Clean Code",
        "authors": [{"name": "Robert C. Martin"}],
        "publishers": [{"name": "Prentice Hall"}],
        "publish_date": "2008",
        "number_of_pages": 464,
        "subjects": [{"name": "Software engineering"}],
        "url": "https://openlibrary.org/books/OL1M",
    }

    def test_main_terminal_format_prints_card(self) -> None:
        with patch("main.fetch_open_library_data", return_value=dict(self.SAMPLE_RAW)):
            code, out, _ = self._run_main(["978-0-13-595705-9"])
        self.assertEqual(code, 0)
        self.assertIn("BOOK INFORMATION (ISBN-13: 9780135957059)", out)
        self.assertIn("Title        : Clean Code", out)

    def test_main_markdown_format_prints_document(self) -> None:
        with patch("main.fetch_open_library_data", return_value=dict(self.SAMPLE_RAW)):
            code, out, _ = self._run_main(["--format", "markdown", "9780135957059"])
        self.assertEqual(code, 0)
        self.assertIn("# Clean Code", out)
        self.assertIn("[Open Library Profile](https://openlibrary.org/books/OL1M)", out)

    def test_main_json_format_writes_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "book.json")
            with patch(
                "main.fetch_open_library_data", return_value=dict(self.SAMPLE_RAW)
            ):
                code, out, _ = self._run_main(
                    ["--format", "json", "-o", out_path, "9780135957059"]
                )
            self.assertEqual(code, 0)
            self.assertIn(f"Book info saved to {out_path}", out)
            with open(out_path, encoding="utf-8") as f:
                saved: Any = json.load(f)
            self.assertEqual(saved["title"], "Clean Code")
            self.assertEqual(saved["isbn"], "9780135957059")


if __name__ == "__main__":
    unittest.main()
