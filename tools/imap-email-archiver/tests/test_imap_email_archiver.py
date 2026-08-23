"""Unit test suite for imap_email_archiver module."""

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

# Ensure script directory is on sys.path for pytest
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import imap_email_archiver as archiver_module  # noqa: E402
from imap_email_archiver import (  # noqa: E402
    archive_imap_emails,
    decode_str,
    main,
    sanitize_filename,
)


def _raw_email(
    subject: str = b"Test Subject",
    date_header: bytes = b"Mon, 15 Jan 2024 10:00:00 +0000",
) -> bytes:
    """Build a minimal RFC822 email for archiving tests."""
    lines = [b"From: sender@example.com", b"Subject: " + subject]
    if date_header is not None:
        lines.append(b"Date: " + date_header)
    lines.extend([b"", b"Hello Email Body"])
    return b"\r\n".join(lines)


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


def test_decode_str_encoded_bytes_header() -> None:
    """Encoded-word headers are decoded from bytes into Unicode."""
    encoded = "=?utf-8?b?UmVwb3J0IMOcYmVy?="
    assert decode_str(encoded) == "Report Über"


def test_decode_str_decode_error_falls_back() -> None:
    """A failing header decode returns the raw value instead of raising."""
    with patch.object(archiver_module, "decode_header", side_effect=Exception("bad")):
        assert decode_str("Raw == Value") == "Raw == Value"


def _make_mock_client(search_ids: bytes = b"1") -> MagicMock:
    """Build a mock IMAP client returning one archivable message."""
    client = MagicMock()
    client.search.return_value = ("OK", [search_ids])
    return client


def test_archive_with_date_filters(tmp_path: Path) -> None:
    """SINCE/BEFORE filters are appended to the IMAP search query."""
    mock_client = _make_mock_client()
    mock_client.fetch.return_value = ("OK", [(b"1", _raw_email())])

    count, out_dir = archive_imap_emails(
        host="imap.example.com",
        user="u",
        password="p",
        output_dir=tmp_path,
        since_date="01-Jan-2024",
        before_date="31-Dec-2024",
        client=mock_client,
    )

    assert count == 1
    query = mock_client.search.call_args[0][1]
    assert 'SINCE "01-Jan-2024"' in query
    assert 'BEFORE "31-Dec-2024"' in query
    assert (out_dir / "2024-01").exists()


def test_archive_real_connection_logout_paths(tmp_path: Path, caplog: Any) -> None:
    """Without an injected client the tool connects and logs out itself."""
    conn = MagicMock()
    conn.search.return_value = ("OK", [b""])
    with patch.object(archiver_module.imaplib, "IMAP4_SSL", return_value=conn):
        count, out_dir = archive_imap_emails(
            host="h", user="u", password="p", output_dir=tmp_path
        )
    assert count == 0
    conn.login.assert_called_once_with("u", "p")
    conn.logout.assert_called_once()

    # A non-empty search result exercises the end-of-run logout too.
    conn2 = MagicMock()
    conn2.search.return_value = ("OK", [b"1"])
    conn2.fetch.return_value = ("OK", [(b"1", _raw_email())])
    with patch.object(archiver_module.imaplib, "IMAP4_SSL", return_value=conn2):
        count2, _ = archive_imap_emails(
            host="h", user="u", password="p", output_dir=tmp_path
        )
    assert count2 == 1
    conn2.logout.assert_called_once()


def test_archive_fetch_failure_skips_message(tmp_path: Path) -> None:
    """Messages whose fetch fails are skipped without aborting the run."""
    mock_client = _make_mock_client(b"1")
    mock_client.fetch.return_value = ("NO", [None])

    count, _ = archive_imap_emails(
        host="h", user="u", password="p", output_dir=tmp_path, client=mock_client
    )
    assert count == 0


def test_archive_empty_body_skips_message(tmp_path: Path) -> None:
    """Fetch responses without a tuple payload produce no .eml files."""
    mock_client = _make_mock_client(b"1")
    mock_client.fetch.return_value = ("OK", [b"FLAGS (\\Seen)"])

    count, out_dir = archive_imap_emails(
        host="h", user="u", password="p", output_dir=tmp_path, client=mock_client
    )
    assert count == 0
    assert list(out_dir.iterdir()) == []


def test_archive_malformed_date_uses_unknown_folder(tmp_path: Path) -> None:
    """Unparseable Date headers fall back to the unknown_date folder."""
    mock_client = _make_mock_client(b"1")
    raw = _raw_email(date_header=b"not-a-real-date-stamp")
    mock_client.fetch.return_value = ("OK", [(b"1", raw)])

    count, out_dir = archive_imap_emails(
        host="h", user="u", password="p", output_dir=tmp_path, client=mock_client
    )
    assert count == 1
    unknown = out_dir / "unknown_date"
    files = list(unknown.glob("0000-00-00_*.eml"))
    assert len(files) == 1


def test_archive_date_parser_exception_is_contained(tmp_path: Path) -> None:
    """An exploding date parser still archives under the fallback name."""
    mock_client = _make_mock_client(b"1")
    mock_client.fetch.return_value = ("OK", [(b"1", _raw_email())])

    with patch.object(archiver_module, "parsedate_tz", side_effect=ValueError("boom")):
        count, out_dir = archive_imap_emails(
            host="h", user="u", password="p", output_dir=tmp_path, client=mock_client
        )
    assert count == 1
    assert (out_dir / "unknown_date").exists()


def test_archive_per_message_exception_continues(tmp_path: Path) -> None:
    """A fetch raising mid-loop is logged and remaining messages proceed."""
    mock_client = _make_mock_client(b"1 2")
    mock_client.fetch.side_effect = [
        RuntimeError("conn dropped"),
        ("OK", [(b"2", _raw_email())]),
    ]

    count, out_dir = archive_imap_emails(
        host="h", user="u", password="p", output_dir=tmp_path, client=mock_client
    )
    assert count == 1
    archived = list((out_dir / "2024-01").glob("*_Test Subject_2.eml"))
    assert len(archived) == 1


def test_archive_outer_failure_returns_zero(tmp_path: Path) -> None:
    """Connection-level failures return gracefully with a zero count."""
    with patch.object(
        archiver_module.imaplib,
        "IMAP4_SSL",
        side_effect=OSError("unreachable"),
    ):
        count, out_dir = archive_imap_emails(
            host="bad.invalid", user="u", password="p", output_dir=tmp_path
        )
    assert count == 0
    assert out_dir.exists()


class TestMainCLI:
    """CLI entry point tests."""

    def test_main_invokes_archiver(self, tmp_path: Path) -> None:
        """The CLI parses flags and forwards them to the archiver."""
        calls: dict = {}

        def fake_archive(**kwargs: Any) -> tuple[int, Path]:
            calls.update(kwargs)
            return 3, tmp_path

        with patch.object(archiver_module, "archive_imap_emails", fake_archive):
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
                    "--since",
                    "01-Jan-2024",
                    "--before",
                    "31-Dec-2024",
                    "-v",
                ]
            )
        assert code == 0
        assert calls["host"] == "imap.example.com"
        assert calls["port"] == 143
        assert calls["mailbox"] == "Sent"
        assert calls["since_date"] == "01-Jan-2024"

    def test_main_requires_host_user_password(self) -> None:
        """Missing required CLI options abort with SystemExit."""
        import pytest

        with pytest.raises(SystemExit):
            main(["--host", "only-host"])
