# Mock pypdf module since it might not be installed
import os
import sys
from unittest.mock import MagicMock, mock_open, patch

sys.modules["pypdf"] = MagicMock()

# Add path to tools/document-deduper to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from document_deduper import (  # noqa: E402
    calculate_jaccard,
    extract_text_docx,
    extract_text_pdf,
    extract_text_txt,
    get_document_text,
    get_shingles,
    main,
    tokenize,
)


def test_extract_text_txt_success():
    with patch("builtins.open", mock_open(read_data="txt content")):
        res = extract_text_txt("fake.txt")
    assert res == "txt content"


def test_extract_text_txt_error():
    with patch("builtins.open", side_effect=OSError("Read error")):
        res = extract_text_txt("fake.txt")
    assert res == ""


def test_extract_text_docx_success():
    xml_data = (
        b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/'
        b'2006/main"><w:t>Hello</w:t><w:t>World</w:t></w:document>'
    )

    mock_zip = MagicMock()
    mock_zip.read.return_value = xml_data
    mock_zip.__enter__.return_value = mock_zip

    with patch("zipfile.ZipFile", return_value=mock_zip):
        result = extract_text_docx("fake.docx")

    assert result == "Hello World"


def test_extract_text_docx_error():
    with patch("zipfile.ZipFile", side_effect=ValueError("Corrupted zip")):
        result = extract_text_docx("fake.docx")
    assert result == ""


def test_extract_text_pdf_success():
    mock_reader = MagicMock()
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "PDF text content"
    mock_reader.pages = [mock_page]

    with patch("document_deduper.HAS_PYPDF", True), patch(
        "pypdf.PdfReader", return_value=mock_reader
    ):
        result = extract_text_pdf("fake.pdf")

    assert result == "PDF text content"


def test_extract_text_pdf_no_pypdf():
    with patch("document_deduper.HAS_PYPDF", False):
        result = extract_text_pdf("fake.pdf")
    assert result == ""


def test_extract_text_pdf_error():
    with patch("document_deduper.HAS_PYPDF", True), patch(
        "pypdf.PdfReader", side_effect=ValueError("Corrupted PDF")
    ):
        result = extract_text_pdf("fake.pdf")
    assert result == ""


def test_get_document_text():
    with patch("document_deduper.extract_text_txt", return_value="txt") as m_txt:
        assert get_document_text("f.txt") == "txt"
        assert get_document_text("f.md") == "txt"
        m_txt.assert_any_call("f.txt")
        m_txt.assert_any_call("f.md")

    with patch("document_deduper.extract_text_docx", return_value="docx") as m_docx:
        assert get_document_text("f.docx") == "docx"
        m_docx.assert_called_once_with("f.docx")

    with patch("document_deduper.extract_text_pdf", return_value="pdf") as m_pdf:
        assert get_document_text("f.pdf") == "pdf"
        m_pdf.assert_called_once_with("f.pdf")

    assert get_document_text("f.unknown") == ""


def test_tokenize():
    text = "Hello, World!  How are you?"
    assert tokenize(text) == ["hello", "world", "how", "are", "you"]
    assert tokenize("") == []


def test_get_shingles():
    tokens = ["a", "b", "c", "d"]
    assert get_shingles(tokens, 3) == {"a b c", "b c d"}
    assert get_shingles(tokens, 5) == set()


def test_calculate_jaccard():
    set1 = {"a", "b", "c"}
    set2 = {"b", "c", "d"}
    assert calculate_jaccard(set1, set2) == 0.5
    assert calculate_jaccard(set(), set2) == 0.0
    assert calculate_jaccard(set1, set()) == 0.0


def test_main_directory_not_found(capsys):
    with patch("os.path.exists", return_value=False), patch(
        "sys.argv", ["document_deduper.py", "missing_dir"]
    ):
        try:
            main()
        except SystemExit as exc:
            assert exc.code == 1
    captured = capsys.readouterr()
    assert "Error: Directory does not exist" in captured.err


def test_main_no_duplicates(capsys):
    with patch("os.path.exists", return_value=True), patch(
        "os.walk", return_value=[("/fake/dir", [], ["file1.txt", "file2.txt"])]
    ), patch("document_deduper.get_document_text") as mock_get_text, patch(
        "sys.argv", ["document_deduper.py", "/fake/dir", "-t", "50", "-s", "2"]
    ):

        mock_get_text.side_effect = lambda path: (
            "hello world" if "file1" in path else "goodbye space"
        )
        main()

    captured = capsys.readouterr()
    assert "Scan Summary: Detected 0 near-duplicate pairs." in captured.out


def test_main_duplicates_found(capsys):
    with patch("os.path.exists", return_value=True), patch(
        "os.walk", return_value=[("/fake/dir", [], ["file1.txt", "file2.txt"])]
    ), patch("document_deduper.get_document_text") as mock_get_text, patch(
        "sys.argv", ["document_deduper.py", "/fake/dir", "-t", "50", "-s", "2"]
    ):

        mock_get_text.side_effect = lambda path: (
            "hello world test" if "file1" in path else "hello world test again"
        )
        main()

    captured = capsys.readouterr()
    assert "[!] MATCH FOUND: Similarity 66.7%" in captured.out
    assert "Scan Summary: Detected 1 near-duplicate pairs." in captured.out


def test_main_skips_small_files(capsys):
    with patch("os.path.exists", return_value=True), patch(
        "os.walk", return_value=[("/fake/dir", [], ["file1.txt"])]
    ), patch("document_deduper.get_document_text", return_value="hello"), patch(
        "sys.argv", ["document_deduper.py", "/fake/dir", "-s", "3"]
    ):
        main()
    captured = capsys.readouterr()
    assert "Loaded 0 text-valid documents" in captured.out
