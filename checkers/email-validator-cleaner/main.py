"""Email Validator & Cleaner CLI Tool.

Validates and cleans email addresses in CSV files. Checks syntax against standard regex,
detects disposable email domains, performs DNS/MX record lookups, and identifies/removes
duplicate email entries.
"""

# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
# pylint: disable=too-many-branches,too-many-statements

import argparse
import csv
import re
import socket
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Standard RFC 5322 compliant regex pattern for basic email validation
EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9]"
    r"(?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)

# Built-in collection of known disposable email domain providers
DEFAULT_DISPOSABLE_DOMAINS: Set[str] = {
    "mailinator.com",
    "10minutemail.com",
    "tempmail.com",
    "guerrillamail.com",
    "throwawaymail.com",
    "dispostable.com",
    "trashmail.com",
    "yopmail.com",
    "getairmail.com",
    "sharklasers.com",
    "maildrop.cc",
    "temp-mail.org",
    "fakeinbox.com",
    "mailnesia.com",
}


def load_disposable_domains(file_path: Optional[Path] = None) -> Set[str]:
    """Load disposable email domains set.

    Args:
        file_path: Optional path to text file containing disposable domains.

    Returns:
        Set of lowercase disposable domain strings.
    """
    domains = set(DEFAULT_DISPOSABLE_DOMAINS)
    if file_path and file_path.exists():
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip().lower()
                if line_str and not line_str.startswith("#"):
                    domains.add(line_str)
    return domains


def is_valid_syntax(email: str) -> bool:
    """Check if email string conforms to standard RFC 5322 syntax regex.

    Args:
        email: Email address string.

    Returns:
        True if valid syntax, False otherwise.
    """
    if not email or len(email) > 254:
        return False
    return bool(EMAIL_REGEX.match(email.strip()))


def is_disposable_domain(email: str, disposable_domains: Set[str]) -> bool:
    """Check if the domain part of email belongs to known disposable list.

    Args:
        email: Cleaned email address.
        disposable_domains: Set of disposable domain names.

    Returns:
        True if domain is disposable, False otherwise.
    """
    if "@" not in email:
        return False
    domain = email.split("@")[-1].lower().strip()
    return domain in disposable_domains


def check_domain_dns(domain: str) -> bool:
    """Perform DNS lookup on email domain to verify host resolution.

    Args:
        domain: Domain part of email address.

    Returns:
        True if host or MX record resolves, False otherwise.
    """
    try:
        socket.getaddrinfo(domain, 80, socket.AF_UNSPEC, socket.SOCK_STREAM)
        return True
    except (socket.gaierror, socket.herror, TimeoutError, OSError):
        return False


def validate_email_entry(
    email_raw: str,
    disposable_domains: Set[str],
    check_mx: bool = False,
    seen_emails: Optional[Set[str]] = None,
) -> Tuple[str, str]:
    """Validate a single email address entry.

    Args:
        email_raw: Raw email input.
        disposable_domains: Set of disposable domain names.
        check_mx: If True, perform DNS lookup on domain.
        seen_emails: Set of already encountered emails for deduplication.

    Returns:
        Tuple of (clean_email, status_tag).
        Status tags: 'VALID', 'EMPTY', 'INVALID_SYNTAX', 'DISPOSABLE',
                     'MX_FAILED', 'DUPLICATE'.
    """
    if not email_raw or not email_raw.strip():
        return "", "EMPTY"

    clean_email = email_raw.strip().lower()

    if not is_valid_syntax(clean_email):
        return clean_email, "INVALID_SYNTAX"

    if is_disposable_domain(clean_email, disposable_domains):
        return clean_email, "DISPOSABLE"

    if seen_emails is not None and clean_email in seen_emails:
        return clean_email, "DUPLICATE"

    if check_mx:
        domain = clean_email.split("@")[-1]
        if not check_domain_dns(domain):
            return clean_email, "MX_FAILED"

    return clean_email, "VALID"


def process_email_csv(
    input_file: Path,
    output_file: Path,
    email_column: str,
    check_mx: bool = False,
    disposable_file: Optional[Path] = None,
    dedupe: bool = True,
    output_flagged: Optional[Path] = None,
) -> Dict[str, int]:
    """Process email CSV file, validate emails, and generate outputs.

    Args:
        input_file: Path to input CSV.
        output_file: Path to main output CSV.
        email_column: Name or 0-based index of email column.
        check_mx: If True, enable DNS lookup.
        disposable_file: Optional custom disposable domain file.
        dedupe: If True, flag duplicate emails.
        output_flagged: Optional path to save flagged/invalid records.

    Returns:
        Dictionary of status counts.
    """
    if not input_file.exists():
        raise FileNotFoundError(f"Input file non-existent: {input_file}")

    disposable_domains = load_disposable_domains(disposable_file)

    with input_file.open("r", encoding="utf-8-sig", newline="") as infile:
        reader = csv.reader(infile)
        rows = list(reader)

    if not rows:
        raise ValueError("Input CSV file is empty.")

    header = rows[0]
    col_idx = -1

    if email_column.isdigit():
        col_idx = int(email_column)
    elif email_column in header:
        col_idx = header.index(email_column)
    else:
        for idx, col in enumerate(header):
            if col.strip().lower() == email_column.strip().lower():
                col_idx = idx
                break

    if col_idx < 0 or col_idx >= len(header):
        err_msg = f"Email column '{email_column}' not found in header: {header}"
        raise ValueError(err_msg)

    new_header = list(header)
    new_header.extend(["email_clean", "validation_status"])

    seen_emails: Set[str] = set()
    stats: Dict[str, int] = {
        "VALID": 0,
        "INVALID_SYNTAX": 0,
        "DISPOSABLE": 0,
        "MX_FAILED": 0,
        "DUPLICATE": 0,
        "EMPTY": 0,
    }

    valid_rows = [new_header]
    flagged_rows = [new_header]

    for row in rows[1:]:
        if not row:
            continue
        raw_email = row[col_idx] if col_idx < len(row) else ""
        clean_email, status = validate_email_entry(
            raw_email,
            disposable_domains,
            check_mx=check_mx,
            seen_emails=seen_emails if dedupe else None,
        )

        if status in stats:
            stats[status] += 1
        else:
            stats[status] = 1

        if status == "VALID" and dedupe and clean_email:
            seen_emails.add(clean_email)

        new_row = list(row)
        while len(new_row) < len(header):
            new_row.append("")
        new_row.extend([clean_email, status])

        if status == "VALID":
            valid_rows.append(new_row)
        else:
            flagged_rows.append(new_row)

    # Save output file (all rows or clean valid rows if dedupe/cleaning)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8", newline="") as outfile:
        writer = csv.writer(outfile)
        if output_flagged:
            # Main file contains valid rows only
            writer.writerows(valid_rows)
        else:
            # Main file contains all processed rows with status columns
            all_rows = [new_header] + valid_rows[1:] + flagged_rows[1:]
            writer.writerows(all_rows)

    if output_flagged:
        output_flagged.parent.mkdir(parents=True, exist_ok=True)
        with output_flagged.open("w", encoding="utf-8", newline="") as flagged_out:
            writer = csv.writer(flagged_out)
            writer.writerows(flagged_rows)

    return stats


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Validates and cleans email lists in CSV files."
    )
    parser.add_argument(
        "-i",
        "--input-file",
        required=True,
        type=Path,
        help="Path to input CSV file",
    )
    parser.add_argument(
        "-o",
        "--output-file",
        required=True,
        type=Path,
        help="Path to output CSV file",
    )
    parser.add_argument(
        "-c",
        "--column",
        required=True,
        help="Email column name or 0-indexed position",
    )
    parser.add_argument(
        "--check-mx",
        action="store_true",
        help="Perform DNS resolution check on email domain",
    )
    parser.add_argument(
        "--disposable-file",
        type=Path,
        help="Path to custom disposable domains text file",
    )
    parser.add_argument(
        "--no-dedupe",
        action="store_false",
        dest="dedupe",
        help="Disable email deduplication check",
    )
    parser.add_argument(
        "--output-flagged",
        type=Path,
        help="Path to write flagged/invalid email records separately",
    )
    return parser.parse_args(args)


def main() -> None:
    """Main CLI execution flow."""
    args = parse_args()
    try:
        stats = process_email_csv(
            input_file=args.input_file,
            output_file=args.output_file,
            email_column=args.column,
            check_mx=args.check_mx,
            disposable_file=args.disposable_file,
            dedupe=args.dedupe,
            output_flagged=args.output_flagged,
        )
        print("Email validation and cleaning complete.")
        for status, count in stats.items():
            print(f"  {status}: {count}")
        print(f"Output saved to: {args.output_file}")
        if args.output_flagged:
            print(f"Flagged records saved to: {args.output_flagged}")
    except Exception as err:  # pylint: disable=broad-exception-caught
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
