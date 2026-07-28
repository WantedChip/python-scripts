"""Downloads attachments from emails matching specific sender or subject filters.

This module connects to IMAP servers, inspects email MIME parts for attachment payloads,
applies filtering criteria, and saves attachments to local destination folders.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-nested-blocks,broad-exception-caught

import argparse
import email
import imaplib
import logging
import re
import sys
from email.header import decode_header
from pathlib import Path
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


def decode_str(header_val: Optional[str]) -> str:
    """Decode MIME header value string.

    Args:
        header_val: Encoded header value string.

    Returns:
        Decoded string.
    """
    if not header_val:
        return ""
    decoded_parts: List[str] = []
    try:
        for part, encoding in decode_header(header_val):
            if isinstance(part, bytes):
                enc = encoding or "utf-8"
                try:
                    decoded_parts.append(part.decode(enc, errors="ignore"))
                except Exception:
                    decoded_parts.append(part.decode("latin-1", errors="ignore"))
            else:
                decoded_parts.append(str(part))
        return "".join(decoded_parts)
    except Exception:
        return str(header_val)


def sanitize_filename(filename: str) -> str:
    """Sanitize attachment filename for safe disk saving.

    Args:
        filename: Raw filename string.

    Returns:
        Cleaned safe filename string.
    """
    clean = re.sub(r'[\\/*?:"<>|]', "_", filename).strip()
    return clean[:120] if clean else "attachment.bin"


def download_email_attachments(
    host: str,
    user: str,
    password: str,
    port: int = 993,
    mailbox: str = "INBOX",
    output_dir: Optional[Path] = None,
    sender_filter: Optional[str] = None,
    subject_filter: Optional[str] = None,
    filename_pattern: Optional[str] = None,
    client: Optional[Any] = None,
) -> Tuple[int, Path]:
    """Download email attachments from IMAP account matching filters.

    Args:
        host: IMAP server host.
        user: Account username or email.
        password: Account password or application token.
        port: Server port (default: 993).
        mailbox: Target IMAP folder (default: INBOX).
        output_dir: Destination folder path.
        sender_filter: Filter sender address string.
        subject_filter: Filter subject string.
        filename_pattern: Filter filename regex pattern.
        client: Optional pre-configured or mock IMAP client instance.

    Returns:
        Tuple containing downloaded attachment count and output directory path.
    """
    target_out = output_dir if output_dir else Path("email_attachments")
    target_out.mkdir(parents=True, exist_ok=True)
    download_count = 0

    try:
        imap_conn = client
        if imap_conn is None:
            imap_conn = imaplib.IMAP4_SSL(host, port)
            imap_conn.login(user, password)

        imap_conn.select(mailbox, readonly=True)

        criteria = ["ALL"]
        if sender_filter:
            criteria.append(f'FROM "{sender_filter}"')
        if subject_filter:
            criteria.append(f'SUBJECT "{subject_filter}"')

        search_query = " ".join(criteria)
        status, data = imap_conn.search(None, search_query)

        if status != "OK" or not data or not data[0]:
            logger.info("No matching emails found in %s.", mailbox)
            if client is None and imap_conn:
                imap_conn.logout()
            return 0, target_out

        msg_ids = data[0].split()
        fn_regex = re.compile(filename_pattern, re.I) if filename_pattern else None

        for msg_id in msg_ids:
            try:
                res_status, msg_data = imap_conn.fetch(msg_id, "(RFC822)")
                if res_status != "OK" or not msg_data or not msg_data[0]:
                    continue

                raw_email = b""
                for part in msg_data:
                    if isinstance(part, tuple) and len(part) >= 2:
                        raw_email = part[1]
                        break

                if not raw_email:
                    continue

                msg = email.message_from_bytes(raw_email)

                for part in msg.walk():
                    if part.get_content_maintype() == "multipart":
                        continue

                    disp = part.get("Content-Disposition", "")
                    filename = part.get_filename()

                    if not filename and "attachment" not in disp.lower():
                        continue

                    raw_fname = filename or "unnamed_attachment"
                    decoded_fname = decode_str(raw_fname)
                    clean_fname = sanitize_filename(decoded_fname)

                    if fn_regex and not fn_regex.search(clean_fname):
                        continue

                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        out_path = target_out / clean_fname
                        with open(out_path, "wb") as f_att:
                            f_att.write(payload)

                        download_count += 1
                        logger.info("Downloaded attachment: %s", clean_fname)

            except Exception as msg_err:
                logger.warning(
                    "Error downloading attachment from email ID %s: %s",
                    msg_id,
                    msg_err,
                )

        if client is None and imap_conn:
            imap_conn.logout()

        return download_count, target_out
    except Exception as err:
        logger.error("Attachment download failed: %s", err)
        return download_count, target_out


def main(args: Optional[List[str]] = None) -> int:
    """Run CLI entry point for email attachment downloader tool.

    Args:
        args: Command line argument list.

    Returns:
        Exit code integer (0 for success, non-zero for failure).
    """
    parser = argparse.ArgumentParser(
        description="Download attachments from emails matching specific filters."
    )
    parser.add_argument("--host", type=str, required=True, help="IMAP server hostname.")
    parser.add_argument(
        "--port", type=int, default=993, help="IMAP server port (default: 993)."
    )
    parser.add_argument(
        "-u", "--user", type=str, required=True, help="IMAP username/email."
    )
    parser.add_argument(
        "-p", "--password", type=str, required=True, help="IMAP password."
    )
    parser.add_argument(
        "-m",
        "--mailbox",
        type=str,
        default="INBOX",
        help="Target IMAP mailbox folder (default: INBOX).",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=str,
        default="email_attachments",
        help="Destination folder for downloaded attachments.",
    )
    parser.add_argument(
        "--from",
        dest="sender",
        type=str,
        default=None,
        help="Filter emails from sender address.",
    )
    parser.add_argument(
        "--subject",
        type=str,
        default=None,
        help="Filter emails with matching subject.",
    )
    parser.add_argument(
        "--filename-pattern",
        type=str,
        default=None,
        help="Filter attachment filenames with regex (e.g. '.*\\.pdf$').",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging."
    )

    parsed_args = parser.parse_args(args)

    level = logging.DEBUG if parsed_args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    out_dir = Path(parsed_args.output_dir)
    count, target_out = download_email_attachments(
        host=parsed_args.host,
        user=parsed_args.user,
        password=parsed_args.password,
        port=parsed_args.port,
        mailbox=parsed_args.mailbox,
        output_dir=out_dir,
        sender_filter=parsed_args.sender,
        subject_filter=parsed_args.subject,
        filename_pattern=parsed_args.filename_pattern,
    )

    logger.info("Downloaded %d attachment(s) to %s", count, target_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
