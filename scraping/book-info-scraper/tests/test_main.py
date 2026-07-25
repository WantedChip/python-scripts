import unittest

from main import (
    BookMetadata,
    clean_isbn,
    format_markdown,
    format_terminal_card,
    parse_book_metadata,
    validate_isbn,
    validate_isbn_10,
    validate_isbn_13,
)


class TestBookInfoScraper(unittest.TestCase):
    """Test suite for ISBN validation and metadata parsing."""

    def test_clean_isbn(self) -> None:
        self.assertEqual(clean_isbn(" 978-0-135957-05-9 "), "9780135957059")
        self.assertEqual(clean_isbn("0-321-57351-x"), "032157351X")

    def test_validate_isbn_10(self) -> None:
        self.assertTrue(validate_isbn_10("032157351X"))
        self.assertTrue(validate_isbn_10("0135957059"))
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


if __name__ == "__main__":
    unittest.main()
