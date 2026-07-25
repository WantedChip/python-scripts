"""SSL/TLS Certificate Expiry Checker.

Checks SSL/TLS certificate expiration dates for target domains and alerts
if expiry falls within a specified threshold of days.
"""

# pylint: disable=too-many-branches,too-many-statements,too-many-locals

import argparse
import datetime
import json
import socket
import ssl
import sys
from typing import Any, Dict, List, Optional


def get_cert_expiry_date(
    domain: str, port: int = 443, timeout: float = 10.0
) -> datetime.datetime:
    """Fetch SSL certificate for a domain and return its expiration datetime (UTC).

    Args:
        domain: Target domain name or IP address.
        port: SSL/TLS port (default 443).
        timeout: Socket connection timeout in seconds.

    Returns:
        datetime.datetime: Expiration date in UTC.

    Raises:
        ValueError: If certificate does not contain 'notAfter' or parsing fails.
        socket.error: If network/socket connection fails.
        ssl.SSLError: If SSL handshake fails.
    """
    context = ssl.create_default_context()
    with socket.create_connection((domain, port), timeout=timeout) as sock:
        with context.wrap_socket(sock, server_hostname=domain) as ssock:
            cert = ssock.getpeercert()
            if not cert or "notAfter" not in cert:
                err = f"No valid SSL certificate found for {domain}:{port}"
                raise ValueError(err)

            # Format: 'MMM DD HH:MM:SS YYYY GMT' e.g. 'May 10 23:59:59 2024 GMT'
            date_str = str(cert["notAfter"])
            expiry_date = datetime.datetime.strptime(date_str, "%b %d %H:%M:%S %Y GMT")
            return expiry_date.replace(tzinfo=datetime.timezone.utc)


def check_domain_expiry(
    domain: str, port: int = 443, warning_days: int = 30, timeout: float = 10.0
) -> Dict[str, Any]:
    """Check certificate expiry for a single domain and evaluate warning status.

    Args:
        domain: Domain name to check.
        port: Port number.
        warning_days: Number of days threshold for warning.
        timeout: Timeout in seconds.

    Returns:
        Dict containing domain details, expiry date, days remaining, warning.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        expiry_date = get_cert_expiry_date(domain, port, timeout)
        days_remaining = (expiry_date - now).days
        is_warning = days_remaining <= warning_days
        is_expired = days_remaining < 0

        status = "EXPIRED" if is_expired else ("WARNING" if is_warning else "OK")

        return {
            "domain": domain,
            "port": port,
            "expiry_date": expiry_date.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "days_remaining": days_remaining,
            "status": status,
            "warning": is_warning or is_expired,
            "error": None,
        }
    except (OSError, ssl.SSLError, ValueError) as exc:
        return {
            "domain": domain,
            "port": port,
            "expiry_date": None,
            "days_remaining": None,
            "status": "ERROR",
            "warning": True,
            "error": str(exc),
        }


def format_report_table(results: List[Dict[str, Any]]) -> str:
    """Format check results into a human-readable ASCII table."""
    headers = ["Domain", "Port", "Expiry Date", "Days Left", "Status"]
    rows = []
    for r in results:
        days = str(r["days_remaining"]) if r["days_remaining"] is not None else "N/A"
        expiry = r["expiry_date"] if r["expiry_date"] else "N/A"
        rows.append([r["domain"], str(r["port"]), expiry, days, r["status"]])

    col_widths = [
        max(len(h), max(len(row[i]) for row in rows)) if rows else len(h)
        for i, h in enumerate(headers)
    ]

    header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    separator = "-+-".join("-" * col_widths[i] for i in range(len(headers)))
    row_lines = [
        " | ".join(row[i].ljust(col_widths[i]) for i in range(len(headers)))
        for row in rows
    ]

    return "\n".join([header_line, separator] + row_lines)


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="SSL/TLS Certificate Expiry Checker")
    parser.add_argument(
        "domains",
        nargs="+",
        help="One or more domains to check (e.g. google.com example.com:8443)",
    )
    parser.add_argument(
        "-w",
        "--warning-days",
        type=int,
        default=30,
        help="Days threshold to trigger warning (default: 30)",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=10.0,
        help="Connection timeout in seconds (default: 10)",
    )
    parser.add_argument(
        "--json", action="store_true", help="Output results in JSON format"
    )

    return parser.parse_args(args)


def main(args: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint for ssl-certificate-expiry-checker."""
    parsed = parse_args(args)

    results = []
    for target in parsed.domains:
        if ":" in target:
            parts = target.split(":")
            domain = parts[0]
            port = int(parts[1])
        else:
            domain = target
            port = 443

        res = check_domain_expiry(
            domain,
            port,
            warning_days=parsed.warning_days,
            timeout=parsed.timeout,
        )
        results.append(res)

    if parsed.json:
        print(json.dumps(results, indent=2))
    else:
        print(format_report_table(results))

    # Exit code 1 if any domain failed or has warning
    if any(r["warning"] for r in results):
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
