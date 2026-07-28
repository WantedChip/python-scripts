"""Unit test suite for imap_email_archiver module."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Ensure script directory is on sys.path for pytest
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from imap_email_archiver import (  # noqa: E402
    archive_imap_emails,
    decode_str,
    sanitize_filename,
)


def test_sanitize_filename() -> None:
    """Test filename sanitization for filesystem safety."""
    assert sanitize_filename("Hello/World: Test?") == "Hello_World_ Test_"
    assert sanitize_filename("") == "untitled_email"


def test_decode_str() -> None:
    """Test MIME header string decoding."""
    assert decode_str("Plain Text") == "Plain Text"
    assert decode_str(None) == ""


def test_archive_imap_emails_mock(tmp_path: Path) -> None:
    """Test archiving IMAP emails using mock client."""
    mock_client = MagicMock()
    mock_client.search.return_value = ("OK", [b"1 2"])
    sample_raw_email = (
        b"From: sender@example.com\r\n"
        b"Subject: Test Subject\r\n"
        b"Date: Mon, 15 Jan 2024 10:00:00 +0000\r\n"
        b"\r\n"
        b"Hello Email Body"
    )
    mock_client.fetch.return_value = ("OK", [(b"1", sample_raw_email)])

    out_dir = tmp_path / "archives"
    count, res_dir = archive_imap_emails(
        host="imap.example.com",
        user="test",
        password="pass",
        output_dir=out_dir,
        client=mock_client,
    )
    assert count == 2
    assert res_dir.exists()
