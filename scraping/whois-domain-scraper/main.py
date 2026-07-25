"""WHOIS Domain Scraper and RDAP Lookup Tool.

Performs WHOIS lookups using RDAP HTTP API or direct TCP WHOIS socket queries,
parses registrar info, creation date, expiration date, name servers, status,
calculates days until expiry, and generates JSON or tabular reports.
"""

# pylint: disable=too-many-branches,too-many-statements
# pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-instance-attributes

import argparse
import json
import re
import socket
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class WhoisInfo:
    """Dataclass holding structured domain WHOIS/RDAP information."""

    domain: str
    registrar: Optional[str] = None
    creation_date: Optional[str] = None
    expiration_date: Optional[str] = None
    days_until_expiry: Optional[int] = None
    name_servers: List[str] = field(default_factory=list)
    status: List[str] = field(default_factory=list)
    query_source: str = "RDAP"
    raw_text: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert object to dictionary."""
        return asdict(self)


def calculate_days_until_expiry(
    expiry_date_str: Optional[str],
) -> Optional[int]:
    """Calculates number of days remaining until domain expiration.

    :param expiry_date_str: ISO format or parsed date string.
    :return: Days remaining as integer, or None if unparseable.
    """
    if not expiry_date_str:
        return None

    # Try common ISO and standard datetime formats
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d-%b-%Y",
    ]

    clean_str = expiry_date_str.strip()
    parsed_dt = None

    for fmt in formats:
        try:
            parsed_dt = datetime.strptime(clean_str, fmt)
            break
        except ValueError:
            continue

    if not parsed_dt:
        # Fallback to regex extraction of YYYY-MM-DD
        match = re.search(r"(\d{4}-\d{2}-\d{2})", clean_str)
        if match:
            try:
                parsed_dt = datetime.strptime(match.group(1), "%Y-%m-%d")
            except ValueError:
                return None
        else:
            return None

    now = datetime.now()
    if parsed_dt.tzinfo is not None:
        now = datetime.now(timezone.utc)

    diff = parsed_dt - now
    return diff.days


def query_rdap(domain: str, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
    """Queries the public RDAP endpoint for domain information.

    :param domain: Domain name to query.
    :param timeout: HTTP request timeout in seconds.
    :return: Parsed JSON dict or None if request fails.
    """
    url = f"https://rdap.org/domain/{domain.strip().lower()}"
    headers = {
        "User-Agent": "WhoisDomainScraper/1.0",
        "Accept": "application/rdap+json, application/json",
    }
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec B310
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                if isinstance(data, dict):
                    return data
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        OSError,
        json.JSONDecodeError,
    ):
        pass
    return None


def parse_rdap_response(domain: str, rdap_data: Dict[str, Any]) -> WhoisInfo:
    """Parses RDAP JSON response into WhoisInfo structure.

    :param domain: Domain name.
    :param rdap_data: RDAP JSON dictionary.
    :return: WhoisInfo dataclass instance.
    """
    info = WhoisInfo(domain=domain, query_source="RDAP")

    # Registrar extraction
    entities = rdap_data.get("entities", [])
    for entity in entities:
        roles = entity.get("roles", [])
        if "registrar" in roles:
            vcard = entity.get("vcardArray", [])
            if len(vcard) > 1 and isinstance(vcard[1], list):
                for item in vcard[1]:
                    is_fn = (
                        isinstance(item, list) and len(item) >= 4 and item[0] == "fn"
                    )
                    if is_fn:
                        info.registrar = item[3]
                        break
            if not info.registrar and "handle" in entity:
                info.registrar = entity["handle"]
            break

    # Events extraction (creation, expiration)
    events = rdap_data.get("events", [])
    for event in events:
        action = event.get("eventAction")
        date_str = event.get("eventDate")
        if action == "registration":
            info.creation_date = date_str
        elif action == "expiration":
            info.expiration_date = date_str

    # Name servers extraction
    ns_list = rdap_data.get("nameservers", [])
    for ns in ns_list:
        ldh_name = ns.get("ldhName")
        if ldh_name:
            info.name_servers.append(ldh_name.lower())

    # Status extraction
    status_list = rdap_data.get("status", [])
    info.status = [s.strip() for s in status_list]

    # Calculate days to expiry
    info.days_until_expiry = calculate_days_until_expiry(info.expiration_date)
    return info


def query_whois_socket(
    domain: str,
    server: str = "whois.iana.org",
    port: int = 43,
    timeout: float = 5.0,
) -> str:
    """Performs raw socket query to port 43 WHOIS server.

    :param domain: Domain name to query.
    :param server: WHOIS server hostname.
    :param port: TCP port number (default 43).
    :param timeout: Socket timeout.
    :return: Raw WHOIS string response.
    """
    domain = domain.strip()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((server, port))
        s.sendall(f"{domain}\r\n".encode("utf-8"))
        response = b""
        while True:
            data = s.recv(4096)
            if not data:
                break
            response += data
        s.close()
        return response.decode("utf-8", errors="ignore")
    except (OSError, socket.error):
        s.close()
        return ""


def parse_whois_text(domain: str, raw_text: str) -> WhoisInfo:
    """Parses key-value fields from raw WHOIS text across various TLD formats.

    :param domain: Target domain name.
    :param raw_text: Raw response string from WHOIS socket query.
    :return: WhoisInfo instance.
    """
    info = WhoisInfo(domain=domain, query_source="WHOIS_SOCKET", raw_text=raw_text)

    # Patterns for key fields
    registrar_patterns = [
        r"(?i)Registrar:\s*(.+)",
        r"(?i)Registrar Name:\s*(.+)",
        r"(?i)Sponsoring Registrar:\s*(.+)",
    ]
    creation_patterns = [
        r"(?i)Creation Date:\s*(.+)",
        r"(?i)Created On:\s*(.+)",
        r"(?i)Registration Time:\s*(.+)",
        r"(?i)Domain Name Commencement Date:\s*(.+)",
    ]
    expiration_patterns = [
        r"(?i)Registry Expiry Date:\s*(.+)",
        r"(?i)Expiration Date:\s*(.+)",
        r"(?i)Paid-till:\s*(.+)",
        r"(?i)Expiry Date:\s*(.+)",
    ]
    ns_patterns = [
        r"(?i)Name Server:\s*(.+)",
        r"(?i)nserver:\s*(.+)",
        r"(?i)Nameservers:\s*(.+)",
    ]
    status_patterns = [
        r"(?i)Domain Status:\s*(.+)",
        r"(?i)Status:\s*(.+)",
    ]

    for pat in registrar_patterns:
        match = re.search(pat, raw_text)
        if match:
            info.registrar = match.group(1).strip()
            break

    for pat in creation_patterns:
        match = re.search(pat, raw_text)
        if match:
            info.creation_date = match.group(1).strip()
            break

    for pat in expiration_patterns:
        match = re.search(pat, raw_text)
        if match:
            info.expiration_date = match.group(1).strip()
            break

    for pat in ns_patterns:
        matches = re.findall(pat, raw_text)
        for m in matches:
            ns_val = m.strip().split()[0].lower()
            if ns_val and ns_val not in info.name_servers:
                info.name_servers.append(ns_val)

    for pat in status_patterns:
        matches = re.findall(pat, raw_text)
        for m in matches:
            st_val = m.strip().split()[0]
            if st_val and st_val not in info.status:
                info.status.append(st_val)

    info.days_until_expiry = calculate_days_until_expiry(info.expiration_date)
    return info


def lookup_domain(domain: str, use_socket_fallback: bool = True) -> WhoisInfo:
    """Performs domain WHOIS lookup using RDAP with optional socket fallback.

    :param domain: Target domain string.
    :param use_socket_fallback: Attempt WHOIS socket query if RDAP fails.
    :return: WhoisInfo object.
    """
    domain = domain.strip().lower()
    rdap_data = query_rdap(domain)
    if rdap_data:
        return parse_rdap_response(domain, rdap_data)

    if use_socket_fallback:
        # First query IANA to find specific WHOIS server
        iana_res = query_whois_socket(domain, "whois.iana.org")
        server = "whois.iana.org"
        match = re.search(r"(?i)refer:\s*(.+)", iana_res)
        if match:
            server = match.group(1).strip()

        raw_res = query_whois_socket(domain, server)
        if raw_res:
            return parse_whois_text(domain, raw_res)

    return WhoisInfo(domain=domain, query_source="FAILED")


def format_table(info_list: List[WhoisInfo]) -> str:
    """Formats a list of WhoisInfo objects into a human-readable table string.

    :param info_list: List of WhoisInfo items.
    :return: Formatted ASCII table string.
    """
    lines = []
    h_dom = f"{'Domain':<25}"
    h_reg = f"{'Registrar':<20}"
    h_exp = f"{'Expires':<12}"
    h_days = f"{'Days Left':<10}"
    h_stat = f"{'Status':<15}"
    header = f"{h_dom} | {h_reg} | {h_exp} | {h_days} | {h_stat}"
    lines.append(header)
    lines.append("-" * len(header))

    for info in info_list:
        domain = info.domain[:24]
        registrar = (info.registrar or "Unknown")[:19]
        expiry = (info.expiration_date or "N/A")[:10]
        if info.days_until_expiry is not None:
            days = str(info.days_until_expiry)
        else:
            days = "N/A"
        status = (info.status[0] if info.status else "Unknown")[:14]
        row_str = (
            f"{domain:<25} | {registrar:<20} | {expiry:<12} | {days:<10} | "
            f"{status:<15}"
        )
        lines.append(row_str)

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    desc = "WHOIS & RDAP Domain Scraper"
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("--domain", "-d", help="Single domain name to lookup")
    parser.add_argument(
        "--file",
        "-f",
        help="File containing list of domain names (one per line)",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file path (prints to stdout if omitted)",
    )
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI entry point for whois-domain-scraper."""
    parser = build_parser()
    parsed = parser.parse_args(args)

    domains = []
    if parsed.domain:
        domains.append(parsed.domain)
    elif parsed.file:
        try:
            with open(parsed.file, "r", encoding="utf-8") as f:
                domains = [
                    line.strip()
                    for line in f
                    if line.strip() and not line.startswith("#")
                ]
        except (OSError, IOError) as e:
            print(f"Error reading file {parsed.file}: {e}", file=sys.stderr)
            return 1
    else:
        parser.print_help()
        return 1

    results = [lookup_domain(d) for d in domains]

    if parsed.format == "json":
        output_str = json.dumps([asdict(r) for r in results], indent=2)
    else:
        output_str = format_table(results)

    if parsed.output:
        with open(parsed.output, "w", encoding="utf-8") as f:
            f.write(output_str + "\n")
        print(f"Results saved to {parsed.output}")
    else:
        print(output_str)

    return 0


if __name__ == "__main__":
    sys.exit(main())
