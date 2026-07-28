"""Unit test suite for email_attachment_downloader module."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Ensure script directory is on sys.path for pytest
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from email_attachment_downloader import (  # noqa: E402
    decode_str,
    download_email_attachments,
    sanitize_filename,
)


def test_sanitize_filename() -> None:
    """Test sanitizing attachment filenames."""
    assert sanitize_filename("doc:1/2?.pdf") == "doc_1_2_.pdf"
    assert sanitize_filename("") == "attachment.bin"


def test_decode_str() -> None:
    """Test MIME header decoding."""
    assert decode_str("report.pdf") == "report.pdf"
    assert decode_str(None) == ""


def test_download_email_attachments_mock(tmp_path: Path) -> None:
    """Test downloading email attachments with mock IMAP client."""
    mock_client = MagicMock()
    mock_client.search.return_value = ("OK", [b"1"])

    sample_raw_email = (
        b"From: sender@example.com\r\n"
        b"Subject: Attachment Email\r\n"
        b'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
        b"\r\n"
        b"--BOUNDARY\r\n"
        b"Content-Type: text/plain\r\n"
        b"\r\n"
        b"Body content\r\n"
        b"--BOUNDARY\r\n"
        b'Content-Type: application/pdf; name="invoice.pdf"\r\n'
        b'Content-Disposition: attachment; filename="invoice.pdf"\r\n'
        b"Content-Transfer-Encoding: base64\r\n"
        b"\r\n"
        b"SGVsbG8gUERG\r\n"
        b"--BOUNDARY--"
    )
    mock_client.fetch.return_value = ("OK", [(b"1", sample_raw_email)])

    out_dir = tmp_path / "attachments"
    count, res_dir = download_email_attachments(
        host="imap.example.com",
        user="test",
        password="pass",
        output_dir=out_dir,
        client=mock_client,
    )
    assert count == 1
    assert (res_dir / "invoice.pdf").exists()
