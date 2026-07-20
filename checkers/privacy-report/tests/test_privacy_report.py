import os
import stat
import sys
from unittest.mock import MagicMock, mock_open, patch

# Add target directory to sys.path so we can import privacy_report
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import privacy_report  # noqa: E402


def test_calculate_entropy():
    # Empty string
    assert privacy_report.calculate_entropy("") == 0.0
    # Single character repeated
    assert privacy_report.calculate_entropy("aaaa") == 0.0
    # Two characters equal frequency
    assert privacy_report.calculate_entropy("abab") == 1.0
    # Four characters equal frequency
    assert privacy_report.calculate_entropy("abcd") == 2.0


def test_check_exif_gps_no_pil():
    with patch("privacy_report.HAS_PIL", False):
        has_gps, msg = privacy_report.check_exif_gps("image.jpg")
        assert has_gps is False
        assert "not installed" in msg


def test_check_exif_gps_no_exif():
    mock_img = MagicMock()
    mock_img._getexif.return_value = None
    mock_img.__enter__.return_value = mock_img
    with patch("privacy_report.HAS_PIL", True), patch(
        "privacy_report.Image.open", return_value=mock_img
    ):
        has_gps, msg = privacy_report.check_exif_gps("image.jpg")
        assert has_gps is False
        assert msg == ""


def test_check_exif_gps_has_gps():
    mock_img = MagicMock()
    mock_img.__enter__.return_value = mock_img
    mock_img._getexif.return_value = {123: {456: "val"}}

    with patch("privacy_report.HAS_PIL", True), patch(
        "privacy_report.Image.open", return_value=mock_img
    ), patch("privacy_report.TAGS", {123: "GPSInfo"}), patch(
        "privacy_report.GPSTAGS", {456: "GPSLatitude"}
    ):

        has_gps, msg = privacy_report.check_exif_gps("image.jpg")
        assert has_gps is True
        assert "GPS metadata found" in msg
        assert "GPSLatitude" in msg


def test_check_exif_gps_error():
    with patch("privacy_report.HAS_PIL", True), patch(
        "privacy_report.Image.open", side_effect=Exception("Read error")
    ):
        has_gps, msg = privacy_report.check_exif_gps("image.jpg")
        assert has_gps is False
        assert "EXIF read error" in msg


def test_check_pdf_metadata_no_pypdf():
    with patch("privacy_report.HAS_PYPDF", False):
        has_meta, msg = privacy_report.check_pdf_metadata("doc.pdf")
        assert has_meta is False
        assert "not installed" in msg


def test_check_pdf_metadata_no_meta():
    mock_reader = MagicMock()
    mock_reader.metadata = None
    with patch("privacy_report.HAS_PYPDF", True), patch(
        "privacy_report.pypdf.PdfReader", return_value=mock_reader
    ):
        has_meta, msg = privacy_report.check_pdf_metadata("doc.pdf")
        assert has_meta is False
        assert msg == ""


def test_check_pdf_metadata_has_meta():
    mock_meta = MagicMock()
    mock_meta.author = "John Doe"
    mock_meta.creator = "PDFCreator"
    mock_meta.producer = "Acrobat"

    mock_reader = MagicMock()
    mock_reader.metadata = mock_meta

    with patch("privacy_report.HAS_PYPDF", True), patch(
        "privacy_report.pypdf.PdfReader", return_value=mock_reader
    ):

        has_meta, msg = privacy_report.check_pdf_metadata("doc.pdf")
        assert has_meta is True
        assert "Metadata fields found" in msg
        assert "Author: John Doe" in msg
        assert "Creator: PDFCreator" in msg
        assert "Producer/Software: Acrobat" in msg


def test_check_pdf_metadata_error():
    with patch("privacy_report.HAS_PYPDF", True), patch(
        "privacy_report.pypdf.PdfReader", side_effect=Exception("PDF error")
    ):
        has_meta, msg = privacy_report.check_pdf_metadata("doc.pdf")
        assert has_meta is False
        assert "PDF read error" in msg


def test_is_hidden_file_dot():
    assert privacy_report.is_hidden_file(".hidden") is True
    assert privacy_report.is_hidden_file("not_hidden") is False


def test_is_hidden_file_windows_attribute():
    mock_stat = MagicMock()
    mock_stat.st_file_attributes = stat.FILE_ATTRIBUTE_HIDDEN

    with patch("sys.platform", "win32"), patch("os.stat", return_value=mock_stat):
        assert privacy_report.is_hidden_file("normal_name") is True


def test_is_hidden_file_windows_attribute_not_hidden():
    mock_stat = MagicMock()
    # No hidden flag
    mock_stat.st_file_attributes = 0

    with patch("sys.platform", "win32"), patch("os.stat", return_value=mock_stat):
        assert privacy_report.is_hidden_file("normal_name") is False


def test_is_hidden_file_windows_oserror():
    with patch("sys.platform", "win32"), patch("os.stat", side_effect=OSError):
        assert privacy_report.is_hidden_file("normal_name") is False


def test_scan_text_file_oserror():
    with patch("builtins.open", side_effect=OSError):
        findings = privacy_report.scan_text_file("file.txt", "john")
        assert findings == []


def test_scan_text_file_findings():
    token_str = "abcdefghijklmnopqrstuvwxyz012345"
    file_content = (
        "Hello john,\n"
        "My email is alice@example.com.\n"
        "Here is a key: aws_key = 'abcdef123456'\n"
        f"And a high entropy token: {token_str}"
    )

    with patch("builtins.open", mock_open(read_data=file_content)):
        findings = privacy_report.scan_text_file("file.txt", "john")

        # Verify username finding
        user_finding = [f for f in findings if "john" in f[1]]
        assert len(user_finding) == 1

        # Verify email finding
        email_finding = [f for f in findings if "alice@example.com" in f[1]]
        assert len(email_finding) == 1

        # Verify aws_key keyword finding
        kw_finding = [f for f in findings if "aws_key" in f[1]]
        assert len(kw_finding) == 1

        # Verify entropy finding
        entropy_finding = [f for f in findings if "High entropy" in f[1]]
        assert len(entropy_finding) == 1


def test_main_dir_not_exists():
    with patch("argparse.ArgumentParser.parse_args") as mock_args, patch(
        "os.path.exists", return_value=False
    ), patch("sys.exit", side_effect=SystemExit) as mock_exit:

        mock_args.return_value = MagicMock(target_dir="nonexistent")
        try:
            privacy_report.main()
        except SystemExit:
            pass
        mock_exit.assert_called_once_with(1)


def test_main_no_leaks():
    with patch("argparse.ArgumentParser.parse_args") as mock_args, patch(
        "os.path.exists", return_value=True
    ), patch("getpass.getuser", return_value="john"), patch(
        "os.walk", return_value=[("/fake", [], [])]
    ), patch(
        "sys.exit", side_effect=SystemExit
    ) as mock_exit:

        mock_args.return_value = MagicMock(target_dir="/fake")
        try:
            privacy_report.main()
        except SystemExit:
            pass
        mock_exit.assert_called_once_with(0)


def test_main_with_leaks():
    walk_data = [
        (
            "/fake",
            ["john"],
            [".hidden_file", "john_doc.txt", "photo.jpg", "document.pdf"],
        )
    ]

    with patch("argparse.ArgumentParser.parse_args") as mock_args, patch(
        "os.path.exists", return_value=True
    ), patch("getpass.getuser", return_value="john"), patch(
        "os.walk", return_value=walk_data
    ), patch(
        "privacy_report.is_hidden_file"
    ) as mock_hidden, patch(
        "privacy_report.check_exif_gps", return_value=(True, "GPS Info")
    ), patch(
        "privacy_report.check_pdf_metadata", return_value=(True, "PDF Meta")
    ), patch(
        "privacy_report.scan_text_file", return_value=[("Warning", "Text leak", 10)]
    ), patch(
        "sys.exit", side_effect=SystemExit
    ) as mock_exit:

        mock_args.return_value = MagicMock(target_dir="/fake")

        # Make is_hidden_file return True for .hidden_file
        mock_hidden.side_effect = lambda path: True if ".hidden" in path else False

        try:
            privacy_report.main()
        except SystemExit:
            pass
        mock_exit.assert_not_called()
