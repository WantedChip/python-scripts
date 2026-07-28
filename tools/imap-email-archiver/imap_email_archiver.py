"""Archives old emails from an IMAP inbox to local folders organized by date.

This module connects to IMAP email servers, searches for messages matching date
filters, and exports raw .eml message files into date-structured local folders.
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
from email.utils import parsedate_tz
from pathlib import Path
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """Sanitize string for safe filesystem filename usage.

    Args:
        name: Raw text name.

    Returns:
        Cleaned filename string.
    """
    clean = re.sub(r'[\\/*?:"<>|]', "_", name).strip()
    return clean[:80] if clean else "untitled_email"


def decode_str(header_val: Optional[str]) -> str:
    """Decode encoded MIME header strings into Unicode.

    Args:
        header_val: Raw encoded MIME header string.

    Returns:
        Decoded string representation.
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


def archive_imap_emails(
    host: str,
    user: str,
    password: str,
    port: int = 993,
    mailbox: str = "INBOX",
    output_dir: Optional[Path] = None,
    since_date: Optional[str] = None,
    before_date: Optional[str] = None,
    client: Optional[Any] = None,
) -> Tuple[int, Path]:
    """Connect to IMAP server and archive matching emails to disk.

    Args:
        host: IMAP server host address.
        user: Account username or email address.
        password: Account password or application token.
        port: Server port (default: 993).
        mailbox: Target IMAP folder (default: INBOX).
        output_dir: Output base path for archives.
        since_date: Optional date filter string.
        before_date: Optional date filter string.
        client: Optional pre-configured or mock IMAP client instance.

    Returns:
        Tuple containing count of archived emails and target output directory path.
    """
    target_out = output_dir if output_dir else Path("email_archive")
    target_out.mkdir(parents=True, exist_ok=True)
    count = 0

    try:
        imap_conn = client
        if imap_conn is None:
            imap_conn = imaplib.IMAP4_SSL(host, port)
            imap_conn.login(user, password)

        imap_conn.select(mailbox, readonly=True)

        criteria = ["ALL"]
        if since_date:
            criteria.append(f'SINCE "{since_date}"')
        if before_date:
            criteria.append(f'BEFORE "{before_date}"')

        search_query = " ".join(criteria)
        status, data = imap_conn.search(None, search_query)

        if status != "OK" or not data or not data[0]:
            logger.info("No matching emails found in %s.", mailbox)
            if client is None and imap_conn:
                imap_conn.logout()
            return 0, target_out

        msg_ids = data[0].split()
        logger.info("Found %d email(s) to archive.", len(msg_ids))

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
                subject = decode_str(msg.get("Subject", "No Subject"))
                date_hdr = msg.get("Date", "")

                date_folder = "unknown_date"
                date_str = "0000-00-00"
                if date_hdr:
                    try:
                        parsed_tuple = parsedate_tz(date_hdr)
                        if parsed_tuple:
                            yr, mo, dy = (
                                parsed_tuple[0],
                                parsed_tuple[1],
                                parsed_tuple[2],
                            )
                            date_folder = f"{yr:04d}-{mo:02d}"
                            date_str = f"{yr:04d}-{mo:02d}-{dy:02d}"
                    except Exception as d_err:
                        logger.debug("Date parsing exception: %s", d_err)

                folder_path = target_out / date_folder
                folder_path.mkdir(parents=True, exist_ok=True)

                id_str = msg_id.decode("utf-8")
                filename = f"{date_str}_{sanitize_filename(subject)}_{id_str}.eml"
                eml_path = folder_path / filename

                with open(eml_path, "wb") as f_eml:
                    f_eml.write(raw_email)

                count += 1
            except Exception as msg_err:
                logger.warning("Error archiving email ID %s: %s", msg_id, msg_err)

        if client is None and imap_conn:
            imap_conn.logout()

        return count, target_out
    except Exception as err:
        logger.error("IMAP archiving failed: %s", err)
        return count, target_out


def main(args: Optional[List[str]] = None) -> int:
    """Run CLI entry point for IMAP email archiver tool.

    Args:
        args: Command line argument list.

    Returns:
        Exit code integer (0 for success, non-zero for failure).
    """
    parser = argparse.ArgumentParser(
        description="Archive old emails from an IMAP inbox to local date folders."
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
        default="email_archive",
        help="Destination directory for email archives.",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="Filter emails since date (e.g. '01-Jan-2024').",
    )
    parser.add_argument(
        "--before",
        type=str,
        default=None,
        help="Filter emails before date (e.g. '31-Dec-2024').",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging."
    )

    parsed_args = parser.parse_args(args)

    level = logging.DEBUG if parsed_args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    out_dir = Path(parsed_args.output_dir)
    count, target_out = archive_imap_emails(
        host=parsed_args.host,
        user=parsed_args.user,
        password=parsed_args.password,
        port=parsed_args.port,
        mailbox=parsed_args.mailbox,
        output_dir=out_dir,
        since_date=parsed_args.since,
        before_date=parsed_args.before,
    )

    logger.info("Archived %d emails to %s", count, target_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
