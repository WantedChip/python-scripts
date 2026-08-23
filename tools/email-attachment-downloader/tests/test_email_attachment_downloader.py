"""Unit test suite for email_attachment_downloader module."""

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

# Ensure script directory is on sys.path for pytest
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import email_attachment_downloader as ead  # noqa: E402
from email_attachment_downloader import (  # noqa: E402
    decode_str,
    download_email_attachments,
    main,
    sanitize_filename,
)


def _raw_email_with_attachment(
    filename: str = "invoice.pdf",
    content: bytes = b"SGVsbG8gUERG",
) -> bytes:
    """Build a minimal RFC822 multipart email carrying one attachment."""
    return (
        b"From: sender@example.com\r\n"
        b"Subject: Attachment Email\r\n"
        b'Content-Type: multipart/mixed; boundary="BOUNDARY"\r\n'
        b"\r\n"
        b"--BOUNDARY\r\n"
        b"Content-Type: text/plain\r\n"
        b"\r\n"
        b"Body content\r\n"
        b"--BOUNDARY\r\n"
        + f'Content-Type: application/pdf; name="{filename}"\r\n'.encode()
        + f'Content-Disposition: attachment; filename="{filename}"\r\n'.encode()
        + b"Content-Transfer-Encoding: base64\r\n"
        b"\r\n" + content + b"\r\n--BOUNDARY--"
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


def test_decode_str_encoded_bytes_header() -> None:
    """Encoded-word headers are decoded from bytes into Unicode."""
    encoded = "=?utf-8?b?YXR0YWNobWVudC5wZGY=?="
    assert decode_str(encoded) == "attachment.pdf"


def test_decode_str_decode_error_falls_back() -> None:
    """A failing header decode returns the raw value instead of raising."""
    with patch.object(ead, "decode_header", side_effect=Exception("bad")):
        assert decode_str("Raw == Value") == "Raw == Value"


def _make_mock_client(search_ids: bytes = b"1") -> MagicMock:
    """Build a mock IMAP client returning one attachment-bearing message."""
    client = MagicMock()
    client.search.return_value = ("OK", [search_ids])
    return client


def test_download_with_sender_and_subject_filters(tmp_path: Path) -> None:
    """Sender/subject filters are appended to the IMAP search query."""
    mock_client = _make_mock_client(b"")
    mock_client.search.return_value = ("OK", [b""])

    download_email_attachments(
        host="imap.example.com",
        user="u",
        password="p",
        output_dir=tmp_path,
        sender_filter="reports@company.com",
        subject_filter="Monthly Report",
        client=mock_client,
    )

    query = mock_client.search.call_args[0][1]
    assert 'FROM "reports@company.com"' in query
    assert 'SUBJECT "Monthly Report"' in query


def test_download_real_connection_logout_paths(tmp_path: Path) -> None:
    """Without an injected client the tool connects and logs out itself."""
    conn = MagicMock()
    conn.search.return_value = ("OK", [b""])
    with patch.object(ead.imaplib, "IMAP4_SSL", return_value=conn):
        count, _ = download_email_attachments(
            host="h", user="u", password="p", output_dir=tmp_path
        )
    assert count == 0
    conn.login.assert_called_once_with("u", "p")
    conn.logout.assert_called_once()

    conn2 = MagicMock()
    conn2.search.return_value = ("OK", [b"1"])
    conn2.fetch.return_value = ("OK", [(b"1", _raw_email_with_attachment())])
    with patch.object(ead.imaplib, "IMAP4_SSL", return_value=conn2):
        count2, out2 = download_email_attachments(
            host="h", user="u", password="p", output_dir=tmp_path
        )
    assert count2 == 1
    assert (out2 / "invoice.pdf").exists()
    conn2.logout.assert_called_once()


def test_download_fetch_failure_skips_message(tmp_path: Path) -> None:
    """Messages whose fetch fails are skipped without aborting the run."""
    mock_client = _make_mock_client(b"1")
    mock_client.fetch.return_value = ("NO", [None])

    count, _ = download_email_attachments(
        host="h", user="u", password="p", output_dir=tmp_path, client=mock_client
    )
    assert count == 0


def test_download_empty_body_skips_message(tmp_path: Path) -> None:
    """Fetch responses lacking a tuple payload produce no files."""
    mock_client = _make_mock_client(b"1")
    mock_client.fetch.return_value = ("OK", [b"FLAGS (\\Seen)"])

    count, out_dir = download_email_attachments(
        host="h", user="u", password="p", output_dir=tmp_path, client=mock_client
    )
    assert count == 0
    assert list(out_dir.iterdir()) == []


def test_download_filename_pattern_filter(tmp_path: Path) -> None:
    """Attachments not matching the filename regex are skipped."""
    mock_client = _make_mock_client(b"1")
    mock_client.fetch.return_value = (
        "OK",
        [(b"1", _raw_email_with_attachment(filename="photo.jpg"))],
    )

    count, out_dir = download_email_attachments(
        host="h",
        user="u",
        password="p",
        output_dir=tmp_path,
        filename_pattern=r".*\.pdf$",
        client=mock_client,
    )
    assert count == 0
    assert list(out_dir.iterdir()) == []


def test_download_attachment_without_filename_gets_default_name(
    tmp_path: Path,
) -> None:
    """Disposition-only attachments are saved under a default name."""
    raw = (
        b"From: s@example.com\r\n"
        b'Subject: blob\r\nContent-Type: multipart/mixed; boundary="B"\r\n'
        b"\r\n--B\r\n"
        b"Content-Type: application/octet-stream\r\n"
        b"Content-Disposition: attachment\r\n\r\n"
        b"aGVsbG8=\r\n--B--"
    )
    mock_client = _make_mock_client(b"1")
    mock_client.fetch.return_value = ("OK", [(b"1", raw)])

    count, out_dir = download_email_attachments(
        host="h", user="u", password="p", output_dir=tmp_path, client=mock_client
    )
    assert count == 1
    assert (out_dir / "unnamed_attachment").exists()


def test_download_per_message_exception_continues(tmp_path: Path) -> None:
    """A fetch raising mid-loop is logged and remaining messages proceed."""
    mock_client = _make_mock_client(b"1 2")
    mock_client.fetch.side_effect = [
        RuntimeError("conn dropped"),
        ("OK", [(b"2", _raw_email_with_attachment())]),
    ]

    count, out_dir = download_email_attachments(
        host="h", user="u", password="p", output_dir=tmp_path, client=mock_client
    )
    assert count == 1
    assert (out_dir / "invoice.pdf").exists()


def test_download_outer_failure_returns_zero(tmp_path: Path) -> None:
    """Connection-level failures return gracefully with a zero count."""
    with patch.object(ead.imaplib, "IMAP4_SSL", side_effect=OSError("unreachable")):
        count, out_dir = download_email_attachments(
            host="bad.invalid", user="u", password="p", output_dir=tmp_path
        )
    assert count == 0
    assert out_dir.exists()


class TestMainCLI:
    """CLI entry point tests."""

    def test_main_invokes_downloader(self, tmp_path: Path) -> None:
        """The CLI parses flags and forwards them to the downloader."""
        calls: dict = {}

        def fake_download(**kwargs: Any) -> tuple[int, Path]:
            calls.update(kwargs)
            return 5, tmp_path

        with patch.object(ead, "download_email_attachments", fake_download):
            code = main(
                [
                    "--host",
                    "imap.example.com",
                    "-u",
                    "user@x",
                    "-p",
                    "pw",
                    "--port",
                    "143",
                    "-m",
                    "Sent",
                    "-o",
                    str(tmp_path),
                    "--from",
                    "a@b.c",
                    "--subject",
                    "Report",
                    "--filename-pattern",
                    r".*\.pdf$",
                    "-v",
                ]
            )
        assert code == 0
        assert calls["host"] == "imap.example.com"
        assert calls["port"] == 143
        assert calls["mailbox"] == "Sent"
        assert calls["sender_filter"] == "a@b.c"
        assert calls["filename_pattern"] == r".*\.pdf$"

    def test_main_requires_host_user_password(self) -> None:
        """Missing required CLI options abort with SystemExit."""
        import pytest

        with pytest.raises(SystemExit):
            main(["--host", "only-host"])
