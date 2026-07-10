"""SSL/Domain Expiry Monitor.

Queries SSL certificates and WHOIS registrar records for domains
to track expiration dates and trigger warnings/critical alerts.
"""

# pylint: disable=duplicate-code
# Standalone script design prioritized over sharing duplicate boilerplate/helpers.


import argparse
import datetime
import json
import logging
import socket
import ssl
import sys
from typing import Any, Dict, List, Optional

# pylint: disable=import-error
import requests
import whois


def get_ssl_expiry(domain: str, port: int = 443) -> Dict[str, Any]:
    """Connects via SSL socket and parses certificate expiration.

    Args:
        domain: Target domain.
        port: HTTPS port.

    Returns:
        Dict of ('expiry_date', 'days_left', 'error').
    """
    context = ssl.create_default_context()
    try:
        with socket.create_connection((domain, port), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
                if not cert:
                    return {
                        "expiry_date": None,
                        "days_left": None,
                        "error": "No certificate",
                    }

                not_after = cert.get("notAfter")
                if not isinstance(not_after, str):
                    return {
                        "expiry_date": None,
                        "days_left": None,
                        "error": "Expiry date missing",
                    }

                if not_after.endswith(" GMT"):
                    not_after = not_after[:-4]
                elif not_after.endswith(" UTC"):
                    not_after = not_after[:-4]

                expiry_dt = datetime.datetime.strptime(not_after, "%b %d %H:%M:%S %Y")
                delta = expiry_dt - datetime.datetime.utcnow()
                return {
                    "expiry_date": expiry_dt.date().isoformat(),
                    "days_left": delta.days,
                    "error": None,
                }
    except Exception as e:  # pylint: disable=broad-except
        return {"expiry_date": None, "days_left": None, "error": str(e)}


def get_domain_expiry(domain: str) -> Dict[str, Any]:
    """Queries WHOIS database for domain expiration.

    Args:
        domain: Target domain.

    Returns:
        Dict of ('expiry_date', 'days_left', 'registrar', 'error').
    """
    try:
        w = whois.whois(domain)
        exp = w.expiration_date
        registrar = w.registrar

        if not exp:
            return {
                "expiry_date": None,
                "days_left": None,
                "registrar": registrar,
                "error": "No expiration date",
            }

        # Handles list formats returned by whois
        if isinstance(exp, list):
            # Select the first datetime in list
            exp_date = exp[0]
        else:
            exp_date = exp

        if not isinstance(exp_date, datetime.datetime):
            return {
                "expiry_date": None,
                "days_left": None,
                "registrar": registrar,
                "error": f"Invalid date type: {type(exp_date)}",
            }

        delta = exp_date - datetime.datetime.utcnow()
        return {
            "expiry_date": exp_date.date().isoformat(),
            "days_left": delta.days,
            "registrar": registrar,
            "error": None,
        }
    except Exception as e:  # pylint: disable=broad-except
        return {
            "expiry_date": None,
            "days_left": None,
            "registrar": None,
            "error": str(e),
        }


def evaluate_status(days_left: Optional[int], warn_days: int, crit_days: int) -> str:
    """Evaluates warning state based on thresholds.

    Args:
        days_left: Remaining days validity.
        warn_days: Warning threshold days.
        crit_days: Critical threshold days.

    Returns:
        Status label.
    """
    if days_left is None:
        return "UNKNOWN"
    if days_left < 0:
        return "EXPIRED"
    if days_left <= crit_days:
        return "CRITICAL"
    if days_left <= warn_days:
        return "WARNING"
    return "HEALTHY"


def check_domain_expiry(
    domain: str, warn_days: int = 30, crit_days: int = 15
) -> Dict[str, Any]:
    """Performs SSL and WHOIS analysis for a single domain.

    Args:
        domain: Domain to query.
        warn_days: Warn days limit.
        crit_days: Critical days limit.

    Returns:
        Consolidated report dictionary.
    """
    logging.info("Checking domain: %s", domain)
    ssl_info = get_ssl_expiry(domain)
    whois_info = get_domain_expiry(domain)

    ssl_status = evaluate_status(ssl_info["days_left"], warn_days, crit_days)
    if ssl_info["error"]:
        ssl_status = "ERROR"

    whois_status = evaluate_status(whois_info["days_left"], warn_days, crit_days)
    if whois_info["error"]:
        whois_status = "ERROR"

    return {
        "domain": domain,
        "ssl": {
            "expiry_date": ssl_info["expiry_date"],
            "days_left": ssl_info["days_left"],
            "status": ssl_status,
            "error": ssl_info["error"],
        },
        "domain_reg": {
            "expiry_date": whois_info["expiry_date"],
            "days_left": whois_info["days_left"],
            "registrar": whois_info["registrar"],
            "status": whois_status,
            "error": whois_info["error"],
        },
    }


def send_webhook(webhook_url: str, alerts: List[str]) -> None:
    """Sends JSON POST request containing warnings list.

    Args:
        webhook_url: Target URL.
        alerts: List of warning message strings.
    """
    if not alerts:
        return
    payload = {
        "content": ("⚠️ **SSL/Domain Expiry Monitor Alert!**\n" + "\n".join(alerts))
    }
    try:
        res = requests.post(webhook_url, json=payload, timeout=10)
        res.raise_for_status()
        logging.info("Webhook alert fired.")
    except Exception as e:  # pylint: disable=broad-except
        logging.error("Failed to fire webhook: %s", e)


def print_report(reports: List[Dict[str, Any]]) -> None:
    """Prints domain status report to stdout.

    Args:
        reports: List of domain expiry reports.
    """
    header_fmt = "{:<25} {:<12} {:<10} {:<12} {:<10}"
    print("=" * 77)
    print(
        header_fmt.format(
            "Domain", "SSL Expiry", "SSL Status", "WHOIS Expiry", "WHOIS Status"
        )
    )
    print("=" * 77)

    for rep in reports:
        ssl_date = rep["ssl"]["expiry_date"] or "ERR/Missing"
        ssl_status = rep["ssl"]["status"]
        whois_date = rep["domain_reg"]["expiry_date"] or "ERR/Missing"
        whois_status = rep["domain_reg"]["status"]

        print(
            header_fmt.format(
                rep["domain"][:25],
                ssl_date,
                ssl_status,
                whois_date,
                whois_status,
            )
        )
        if rep["ssl"]["error"]:
            print(f"  - SSL Error: {rep['ssl']['error']}")
        if rep["domain_reg"]["error"]:
            print(f"  - WHOIS Error: {rep['domain_reg']['error']}")
        if rep["ssl"]["error"] or rep["domain_reg"]["error"]:
            print("-" * 77)

    print("=" * 77)


def main(argv: Optional[List[str]] = None) -> None:  # pylint: disable=too-many-branches
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "SSL/Domain Expiry Monitor: Track certificate and WHOIS "
            "registration expirations."
        )
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-d", "--domains", nargs="+", help="Space-separated list of domains to check"
    )
    group.add_argument(
        "-f", "--file", help="Path to text file containing domains (one per line)"
    )

    parser.add_argument(
        "-w",
        "--warn-threshold",
        type=int,
        default=30,
        help="Warning threshold days (default: 30)",
    )
    parser.add_argument(
        "-c",
        "--crit-threshold",
        type=int,
        default=15,
        help="Critical threshold days (default: 15)",
    )
    parser.add_argument(
        "--webhook",
        help="Webhook URL to post JSON alerts",
    )
    parser.add_argument(
        "-j", "--json-output", action="store_true", help="Output results in JSON format"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args(argv)

    # Configure logging
    log_level = logging.INFO if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    domains = []
    if args.domains:
        domains = args.domains
    elif args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                domains = [
                    line.strip()
                    for line in f
                    if line.strip() and not line.startswith("#")
                ]
        except FileNotFoundError:
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            sys.exit(2)

    reports = []
    alerts = []
    has_failure = False

    for domain in domains:
        rep = check_domain_expiry(domain, args.warn_threshold, args.crit_threshold)
        reports.append(rep)

        # Audit SSL status
        if rep["ssl"]["status"] in ("EXPIRED", "CRITICAL", "WARNING"):
            alerts.append(
                f"• SSL for `{domain}` is {rep['ssl']['status']} "
                f"({rep['ssl']['days_left']} days left)"
            )
            if rep["ssl"]["status"] in ("EXPIRED", "CRITICAL"):
                has_failure = True
        elif rep["ssl"]["status"] == "ERROR":
            alerts.append(f"• SSL check for `{domain}` failed: {rep['ssl']['error']}")
            has_failure = True

        # Audit WHOIS status
        if rep["domain_reg"]["status"] in ("EXPIRED", "CRITICAL", "WARNING"):
            alerts.append(
                f"• Domain registration for `{domain}` is "
                f"{rep['domain_reg']['status']} "
                f"({rep['domain_reg']['days_left']} days left)"
            )
            if rep["domain_reg"]["status"] in ("EXPIRED", "CRITICAL"):
                has_failure = True
        elif rep["domain_reg"]["status"] == "ERROR":
            alerts.append(
                f"• WHOIS check for `{domain}` failed: {rep['domain_reg']['error']}"
            )
            has_failure = True

    if args.json_output:
        print(json.dumps(reports, indent=2))
    else:
        print_report(reports)

    if args.webhook and alerts:
        send_webhook(args.webhook, alerts)

    sys.exit(1 if has_failure else 0)


if __name__ == "__main__":
    main()
