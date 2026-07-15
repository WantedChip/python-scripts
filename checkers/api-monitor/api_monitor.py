"""API Health Monitor.

Tests HTTP endpoints for status codes, latency thresholds, JSON schemas,
and SSL certificate expiration warnings.
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
import time
import urllib.parse
from typing import Any, Dict, List, Optional

# pylint: disable=import-error
import jsonschema
import requests
import yaml


def check_ssl_expiry(url: str, warn_days: int = 15) -> Dict[str, Any]:
    """Retrieves remaining SSL certificate validity days.

    Args:
        url: Target endpoint URL.
        warn_days: Threshold days to trigger warning.

    Returns:
        Dict detailing SSL status ('status', 'days_left', 'error').
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        return {"status": "skipped", "days_left": None, "error": None}

    hostname = parsed.hostname
    if not hostname:
        return {"status": "error", "days_left": None, "error": "Invalid hostname"}

    port = parsed.port or 443
    context = ssl.create_default_context()

    try:
        with socket.create_connection((hostname, port), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                if not cert:
                    return {
                        "status": "error",
                        "days_left": None,
                        "error": "No certificate found",
                    }

                # Example format: 'Nov 25 12:00:00 2026 GMT'
                not_after_str = cert.get("notAfter")
                if not isinstance(not_after_str, str):
                    return {
                        "status": "error",
                        "days_left": None,
                        "error": "No expiry date in cert",
                    }

                # Strip GMT if present at the end for strptime parsing
                if not_after_str.endswith(" GMT"):
                    not_after_str = not_after_str[:-4]
                elif not_after_str.endswith(" UTC"):
                    not_after_str = not_after_str[:-4]

                expiry_dt = datetime.datetime.strptime(
                    not_after_str, "%b %d %H:%M:%S %Y"
                )
                delta = expiry_dt - datetime.datetime.utcnow()
                days_left = delta.days

                if days_left < 0:
                    status = "expired"
                elif days_left <= warn_days:
                    status = "warning"
                else:
                    status = "healthy"

                return {"status": status, "days_left": days_left, "error": None}

    except Exception as e:  # pylint: disable=broad-except
        return {"status": "error", "days_left": None, "error": str(e)}


def test_endpoint(
    endpoint: Dict[str, Any],
) -> Dict[str, Any]:
    # pylint: disable=too-many-locals,too-many-statements
    """Tests a single endpoint.

    Args:
        endpoint: Configuration dictionary for the endpoint.

    Returns:
        A dictionary containing the health report.
    """
    name = endpoint.get("name", "Unnamed Endpoint")
    url = endpoint.get("url")
    method = endpoint.get("method", "GET").upper()
    headers = endpoint.get("headers")
    payload = endpoint.get("payload")
    expected_status = endpoint.get("expected_status", 200)
    latency_threshold = endpoint.get("latency_threshold_ms", 1000)
    schema = endpoint.get("schema")
    warn_ssl_days = endpoint.get("warn_ssl_days", 15)

    report = {
        "name": name,
        "url": url,
        "method": method,
        "status_code": None,
        "latency_ms": None,
        "latency_ok": True,
        "status_ok": True,
        "schema_ok": True,
        "ssl_status": "skipped",
        "ssl_days": None,
        "ssl_error": None,
        "errors": [],
    }

    if not url:
        report["status_ok"] = False
        report["errors"].append("Missing target URL")
        return report

    # 1. SSL check
    ssl_info = check_ssl_expiry(url, warn_ssl_days)
    report["ssl_status"] = ssl_info["status"]
    report["ssl_days"] = ssl_info["days_left"]
    if ssl_info["error"]:
        report["ssl_error"] = ssl_info["error"]
        report["errors"].append(f"SSL Check Error: {ssl_info['error']}")
    elif ssl_info["status"] in ("expired", "warning"):
        report["errors"].append(
            f"SSL Certificate is {ssl_info['status'].upper()} "
            f"({ssl_info['days_left']} days remaining)"
        )

    # 2. HTTP Request
    try:
        start_time = time.perf_counter()
        # Timeout at 10 seconds
        if method == "POST":
            res = requests.post(url, json=payload, headers=headers, timeout=10)
        else:
            res = requests.get(url, params=payload, headers=headers, timeout=10)
        end_time = time.perf_counter()

        latency = int((end_time - start_time) * 1000)
        report["latency_ms"] = latency
        report["status_code"] = res.status_code

        # Latency check
        if latency > latency_threshold:
            report["latency_ok"] = False
            report["errors"].append(
                f"Latency exceeded threshold: " f"{latency}ms > {latency_threshold}ms"
            )

        # Status check
        if res.status_code != expected_status:
            report["status_ok"] = False
            report["errors"].append(
                f"Status code mismatch: "
                f"got {res.status_code}, expected {expected_status}"
            )

        # JSON Schema validation
        if schema:
            try:
                data = res.json()
                jsonschema.validate(instance=data, schema=schema)
            except requests.exceptions.JSONDecodeError:
                report["schema_ok"] = False
                report["errors"].append(
                    "Failed to decode JSON response for schema validation"
                )
            except jsonschema.ValidationError as err:
                report["schema_ok"] = False
                report["errors"].append(f"JSON Schema Validation Error: {err.message}")

    except requests.exceptions.RequestException as e:
        report["status_ok"] = False
        report["errors"].append(f"HTTP Request failed: {e}")

    return report


def run_monitor(config_path: str) -> List[Dict[str, Any]]:
    """Loads config and tests all endpoints.

    Args:
        config_path: Path to config YAML or JSON.

    Returns:
        List of reports.
    """
    with open(config_path, "r", encoding="utf-8") as f:
        if config_path.endswith((".yaml", ".yml")):
            config = yaml.safe_load(f)
        else:
            config = json.load(f)

    endpoints = config.get("endpoints", [])
    reports = []
    for ep in endpoints:
        reports.append(test_endpoint(ep))
    return reports


def print_table(reports: List[Dict[str, Any]]) -> None:
    """Prints final summary table.

    Args:
        reports: List of endpoint reports.
    """
    header_fmt = "{:<25} {:<6} {:<10} {:<10} {:<10} {:<10}"
    print("=" * 77)
    print(
        header_fmt.format(
            "Endpoint", "Method", "HTTP Status", "Latency", "SSL Days", "Result"
        )
    )
    print("=" * 77)

    for rep in reports:
        # Determine overall result
        is_failed = (
            not rep["status_ok"]
            or not rep["latency_ok"]
            or not rep["schema_ok"]
            or rep["ssl_status"] == "expired"
        )
        result = "FAILED" if is_failed else "HEALTHY"

        status_str = str(rep["status_code"]) if rep["status_code"] else "ERR"
        latency_str = f"{rep['latency_ms']}ms" if rep["latency_ms"] else "-"
        ssl_str = str(rep["ssl_days"]) if rep["ssl_days"] is not None else "-"

        print(
            header_fmt.format(
                rep["name"][:25],
                rep["method"],
                status_str,
                latency_str,
                ssl_str,
                result,
            )
        )
        if rep["errors"]:
            for err in rep["errors"]:
                print(f"  - ERROR: {err}")
            print("-" * 77)

    print("=" * 77)


def main(argv: Optional[List[str]] = None) -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "API Health Monitor: Periodically test endpoints for "
            "status, latency, schemas, and SSL expiration."
        )
    )
    parser.add_argument(
        "-c",
        "--config",
        required=True,
        help="Path to YAML or JSON config file",
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

    try:
        reports = run_monitor(args.config)

        if args.json_output:
            print(json.dumps(reports, indent=2))
        else:
            print_table(reports)

        # Exit code 1 if any endpoints failed
        has_failure = any(
            not r["status_ok"]
            or not r["latency_ok"]
            or not r["schema_ok"]
            or r["ssl_status"] == "expired"
            for r in reports
        )
        sys.exit(1 if has_failure else 0)

    except FileNotFoundError as e:
        print(f"Error: Config file not found: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:  # pylint: disable=broad-except
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
