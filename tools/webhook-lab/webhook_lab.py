#!/usr/bin/env python3
"""Webhook Lab — local HTTP webhook receiver, inspector, replay, and verify tool.

Supports SQLite archiving, Unified Diffing, Request forwarding (replaying),
HMAC-SHA256 signature verification (GitHub/Stripe styles), and secret redaction.
"""

import argparse
import difflib
import hmac
import http.server
import json
import logging
import sqlite3
import sys
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# Set up logger
logger = logging.getLogger("webhook_lab")


def setup_logging(verbose: bool) -> None:
    """Configure logger verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.setLevel(level)
    logger.addHandler(handler)


class WebhookDatabase:
    """SQLite wrapper for archiving incoming HTTP webhook requests."""

    def __init__(self, db_path: str) -> None:
        """Initialize the SQLite database and schemas."""
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._create_table()

    def _create_table(self) -> None:
        """Create the request log table with verification status."""
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    headers TEXT NOT NULL,
                    body TEXT NOT NULL,
                    verified INTEGER NOT NULL DEFAULT -1
                )
                """
            )

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def insert_request(
        self, method: str, path: str, headers: Dict[str, str], body: str, verified: int
    ) -> int:
        """Insert a logged request and return its generated ID."""
        now = datetime.now().isoformat()
        headers_str = json.dumps(headers)
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO requests (timestamp, method, path, headers, body, verified)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now, method, path, headers_str, body, verified),
            )
            row_id = cursor.lastrowid
            if row_id is None:
                raise sqlite3.DatabaseError("Failed to retrieve inserted row ID.")
            return int(row_id)

    def get_requests(self) -> List[Dict[str, Any]]:
        """Retrieve all logged requests from the database."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, timestamp, method, path, headers, body, verified "
            "FROM requests ORDER BY id DESC"
        )
        rows = cursor.fetchall()
        requests = []
        for r in rows:
            requests.append(
                {
                    "id": r[0],
                    "timestamp": r[1],
                    "method": r[2],
                    "path": r[3],
                    "headers": json.loads(r[4]),
                    "body": r[5],
                    "verified": r[6],
                }
            )
        return requests

    def get_request(self, req_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve a specific request by ID."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, timestamp, method, path, headers, body, verified "
            "FROM requests WHERE id = ?",
            (req_id,),
        )
        r = cursor.fetchone()
        if not r:
            return None
        return {
            "id": r[0],
            "timestamp": r[1],
            "method": r[2],
            "path": r[3],
            "headers": json.loads(r[4]),
            "body": r[5],
            "verified": r[6],
        }

    def close(self) -> None:
        """Close SQLite database connection."""
        self.conn.close()


# pylint: disable=too-many-locals,too-many-return-statements
def verify_signature(
    body_bytes: bytes,
    headers: Dict[str, str],
    sig_header: Optional[str],
    sig_secret: Optional[str],
    sig_style: str,
) -> int:
    """Verify HMAC signature of the request body against specified style."""
    if not sig_header or not sig_secret:
        return -1

    sig_val = ""
    for k, v in headers.items():
        if k.lower() == sig_header.lower():
            sig_val = v
            break

    if not sig_val:
        logger.warning("Signature header '%s' missing from request.", sig_header)
        return 0

    secret_bytes = sig_secret.encode("utf-8")

    try:
        if sig_style == "stripe":
            parts = {
                k.strip(): v.strip()
                for part in sig_val.split(",")
                if "=" in part
                for k, v in [part.split("=", 1)]
            }
            timestamp = parts.get("t")
            signature = parts.get("v1")
            if not timestamp or not signature:
                return 0

            sign_payload = timestamp.encode("utf-8") + b"." + body_bytes
            mac = hmac.new(secret_bytes, sign_payload, "sha256")
            expected = mac.hexdigest()
            return int(hmac.compare_digest(expected, signature))

        if sig_style == "github":
            if sig_val.startswith("sha256="):
                sig_val = sig_val.removeprefix("sha256=")
            mac = hmac.new(secret_bytes, body_bytes, "sha256")
            expected = mac.hexdigest()
            return int(hmac.compare_digest(expected, sig_val))

        mac = hmac.new(secret_bytes, body_bytes, "sha256")
        expected = mac.hexdigest()
        return int(hmac.compare_digest(expected, sig_val))

    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.error("Error occurred verifying signature: %s", err)
        return 0


def redact_json(data: Any, redact_keys: List[str]) -> Any:
    """Recursively redact keys matching case-insensitively in JSON dicts/lists."""
    redact_keys_lower = [k.lower() for k in redact_keys]
    if isinstance(data, dict):
        new_dict = {}
        for k, v in data.items():
            if k.lower() in redact_keys_lower:
                new_dict[k] = "[REDACTED]"
            else:
                new_dict[k] = redact_json(v, redact_keys)
        return new_dict
    if isinstance(data, list):
        return [redact_json(item, redact_keys) for item in data]
    return data


def redact_payload(
    headers: Dict[str, str], body: str, redact_keys: List[str]
) -> Tuple[Dict[str, str], str]:
    """Redact sensitive headers and body fields based on redact_keys."""
    if not redact_keys:
        return headers, body

    redact_keys_lower = [k.lower() for k in redact_keys]

    redacted_headers = {}
    for k, v in headers.items():
        if k.lower() in redact_keys_lower:
            redacted_headers[k] = "[REDACTED]"
        else:
            redacted_headers[k] = v

    redacted_body = body
    if body:
        try:
            parsed = json.loads(body)
            redacted_json_obj = redact_json(parsed, redact_keys)
            redacted_body = json.dumps(redacted_json_obj, indent=2)
        except ValueError:
            pass

    return redacted_headers, redacted_body


class WebhookHTTPHandler(http.server.BaseHTTPRequestHandler):
    """HTTP Request Handler that verifies signatures and records webhooks."""

    def log_message(self, format_str: str, *args: Any) -> None:
        """Silence standard server log output."""
        # pylint: disable=arguments-differ
        logger.debug(format_str, *args)

    def do_request(self) -> None:
        """Read request body, run signature verification, save, and respond."""
        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = b""
        if content_length > 0:
            try:
                body_bytes = self.rfile.read(content_length)
            except OSError as e:
                logger.error("Failed to read request body: %s", e)

        body_str = body_bytes.decode("utf-8", errors="replace")
        headers_dict = dict(self.headers.items())

        server_instance: Any = self.server
        db: WebhookDatabase = server_instance.db
        sig_header: Optional[str] = server_instance.sig_header
        sig_secret: Optional[str] = server_instance.sig_secret
        sig_style: str = server_instance.sig_style

        verified = verify_signature(
            body_bytes, headers_dict, sig_header, sig_secret, sig_style
        )

        if verified == 0:
            logger.warning("Webhook received with INVALID signature.")
            try:
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                err_resp: Dict[str, Any] = {
                    "status": "unauthorized",
                    "error": "Invalid signature",
                }
                self.wfile.write(json.dumps(err_resp).encode("utf-8"))
            except OSError as e:
                logger.error("Failed to respond to client: %s", e)
            return

        req_id = db.insert_request(
            self.command, self.path, headers_dict, body_str, verified
        )
        ver_status = "VERIFIED" if verified == 1 else "UNCHECKED"
        logger.info(
            "Received Webhook [ID: %d] [%s] %s %s from %s",
            req_id,
            ver_status,
            self.command,
            self.path,
            self.client_address[0],
        )

        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            ok_resp: Dict[str, Any] = {"status": "ok", "request_id": req_id}
            self.wfile.write(json.dumps(ok_resp).encode("utf-8"))
        except OSError as e:
            logger.error("Failed to respond to client: %s", e)

    def do_GET(self) -> None:  # pylint: disable=invalid-name
        """Handle GET requests."""
        self.do_request()

    def do_POST(self) -> None:  # pylint: disable=invalid-name
        """Handle POST requests."""
        self.do_request()

    def do_PUT(self) -> None:  # pylint: disable=invalid-name
        """Handle PUT requests."""
        self.do_request()

    def do_PATCH(self) -> None:  # pylint: disable=invalid-name
        """Handle PATCH requests."""
        self.do_request()

    def do_DELETE(self) -> None:  # pylint: disable=invalid-name
        """Handle DELETE requests."""
        self.do_request()


class WebhookServer(http.server.ThreadingHTTPServer):
    """Custom HTTPServer holding config and database references."""

    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def __init__(
        self,
        server_address: Tuple[str, int],
        db: WebhookDatabase,
        sig_header: Optional[str],
        sig_secret: Optional[str],
        sig_style: str,
    ) -> None:
        """Initialize server with custom DB reference and signature rules."""
        self.db = db
        self.sig_header = sig_header
        self.sig_secret = sig_secret
        self.sig_style = sig_style
        super().__init__(server_address, WebhookHTTPHandler)


# pylint: disable=too-many-arguments,too-many-positional-arguments
def start_server(
    host: str,
    port: int,
    db_path: str,
    sig_header: Optional[str],
    sig_secret: Optional[str],
    sig_style: str,
) -> None:
    """Launch local HTTP Webhook Lab receiver."""
    db = WebhookDatabase(db_path)
    server = WebhookServer((host, port), db, sig_header, sig_secret, sig_style)
    logger.info("Starting Webhook Lab Server on %s:%d ...", host, port)
    if sig_header and sig_secret:
        logger.info(
            "Signature Verification Active: header=%s style=%s",
            sig_header,
            sig_style,
        )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down Webhook Lab Server.")
    finally:
        server.server_close()
        db.close()


def list_requests(db_path: str) -> None:
    """List captured requests."""
    db = WebhookDatabase(db_path)
    requests = db.get_requests()
    db.close()

    if not requests:
        logger.info("No captured webhook requests found in database.")
        return

    headers_str = (
        f"{'ID':<5} | {'TIMESTAMP':<25} | {'METHOD':<8} | {'PATH':<25} | "
        f"{'VERIFIED':<10}"
    )
    print(headers_str)
    print("-" * 80)
    for r in requests:
        path = r["path"]
        if len(path) > 22:
            path = path[:19] + "..."
        verified = r["verified"]
        ver_str = "SUCCESS" if verified == 1 else ("FAILED" if verified == 0 else "N/A")
        fmt_line = (
            f"{r['id']:<5} | {r['timestamp']:<25} | {r['method']:<8} | "
            f"{path:<25} | {ver_str:<10}"
        )
        print(fmt_line)
    print("-" * 80)


def show_request(db_path: str, req_id: int, redact_keys: List[str]) -> None:
    """Display headers and payload for a specific request ID."""
    db = WebhookDatabase(db_path)
    r = db.get_request(req_id)
    db.close()

    if not r:
        logger.error("Request ID %d not found in database.", req_id)
        sys.exit(1)

    red_headers, red_body = redact_payload(r["headers"], r["body"], redact_keys)

    verified = r["verified"]
    ver_str = "SUCCESS" if verified == 1 else ("FAILED" if verified == 0 else "N/A")

    print(f"Request ID: {r['id']}")
    print(f"Timestamp : {r['timestamp']}")
    print(f"Method    : {r['method']}")
    print(f"Path      : {r['path']}")
    print(f"Signature : {ver_str}")
    print("\nHeaders:")
    for k, v in red_headers.items():
        print(f"  {k}: {v}")
    print("\nBody:")
    if not red_body:
        print("  (Empty Body)")
    else:
        print(red_body)


# pylint: disable=too-many-locals
def replay_request(
    db_path: str, req_id: int, target_url: str, redact_keys: List[str]
) -> None:
    """Replay request headers and payload to another endpoint."""
    db = WebhookDatabase(db_path)
    r = db.get_request(req_id)
    db.close()

    if not r:
        logger.error("Request ID %d not found in database.", req_id)
        sys.exit(1)

    logger.info("Replaying request ID %d to URL %s ...", req_id, target_url)

    red_headers, red_body = redact_payload(r["headers"], r["body"], redact_keys)

    exclude_headers = {"host", "connection", "content-length"}
    headers = {k: v for k, v in red_headers.items() if k.lower() not in exclude_headers}

    body_bytes = red_body.encode("utf-8") if red_body else b""

    req = urllib.request.Request(
        target_url,
        data=body_bytes if r["method"] in {"POST", "PUT", "PATCH"} else None,
        headers=headers,
        method=r["method"],
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:  # nosec B310
            status = response.status
            resp_body = response.read().decode("utf-8")
            logger.info("Replay Status: %d", status)
            logger.info("Replay Response:\n%s", resp_body)
    except urllib.error.HTTPError as e:
        logger.error("Replay HTTP Error: %d - %s", e.code, e.read().decode("utf-8"))
        sys.exit(1)
    except (OSError, urllib.error.URLError) as e:
        logger.error("Failed to replay request: %s", e)
        sys.exit(1)


# pylint: disable=too-many-locals
def compare_requests(
    db_path: str, req_id_a: int, req_id_b: int, redact_keys: List[str]
) -> None:
    """Diff the headers and body of two requests."""
    db = WebhookDatabase(db_path)
    req_a = db.get_request(req_id_a)
    req_b = db.get_request(req_id_b)
    db.close()

    if not req_a:
        logger.error("Request ID %d not found in database.", req_id_a)
        sys.exit(1)
    if not req_b:
        logger.error("Request ID %d not found in database.", req_id_b)
        sys.exit(1)

    logger.info("Comparing request ID %d against request ID %d:", req_id_a, req_id_b)

    red_headers_a, red_body_a = redact_payload(
        req_a["headers"], req_a["body"], redact_keys
    )
    red_headers_b, red_body_b = redact_payload(
        req_b["headers"], req_b["body"], redact_keys
    )

    lines_a = [
        f"Method: {req_a['method']}",
        f"Path: {req_a['path']}",
        "Headers:",
    ]
    for k, v in sorted(red_headers_a.items()):
        lines_a.append(f"  {k}: {v}")
    lines_a.append("Body:")
    lines_a.extend(red_body_a.splitlines())

    lines_b = [
        f"Method: {req_b['method']}",
        f"Path: {req_b['path']}",
        "Headers:",
    ]
    for k, v in sorted(red_headers_b.items()):
        lines_b.append(f"  {k}: {v}")
    lines_b.append("Body:")
    lines_b.extend(red_body_b.splitlines())

    diff = list(
        difflib.unified_diff(
            lines_a,
            lines_b,
            fromfile=f"Request_{req_id_a}",
            tofile=f"Request_{req_id_b}",
            lineterm="",
        )
    )

    if not diff:
        logger.info("Requests are completely identical.")
    else:
        print("\nUnified Differences:")
        for line in diff:
            print(line)


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Webhook Lab: Local webhook receiver, "
            "inspect request history, replay, diff, and verify signatures."
        )
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="webhook_lab.db",
        help="Path to SQLite database file (default: webhook_lab.db)",
    )
    parser.add_argument(
        "--redact-keys",
        type=str,
        default="Authorization,Cookie,X-Api-Key,password,token,secret,key",
        help="Comma-separated keys to redact from header and body",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable detailed log descriptions",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start", help="Start the webhook receiver")
    start_parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Hostname/IP to bind to (default: 127.0.0.1)",
    )
    start_parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="TCP port to listen on (default: 8080)",
    )
    start_parser.add_argument(
        "--sig-header",
        type=str,
        help="HTTP header key containing the signature (e.g. X-Hub-Signature-256)",
    )
    start_parser.add_argument(
        "--sig-secret",
        type=str,
        help="HMAC secret key to verify signatures",
    )
    start_parser.add_argument(
        "--sig-style",
        choices=["raw-hmac", "github", "stripe"],
        default="raw-hmac",
        help="Verification method style (default: raw-hmac)",
    )

    subparsers.add_parser("list", help="List all received requests")

    show_parser = subparsers.add_parser("show", help="Display details of a request")
    show_parser.add_argument("id", type=int, help="Request database ID")

    replay_parser = subparsers.add_parser(
        "replay", help="Replay a request to target URL"
    )
    replay_parser.add_argument("id", type=int, help="Request database ID to replay")
    replay_parser.add_argument(
        "--to",
        dest="target_url",
        required=True,
        help="HTTP endpoint URL to replay to",
    )

    compare_parser = subparsers.add_parser(
        "compare", help="Compare two request payloads"
    )
    compare_parser.add_argument("id_a", type=int, help="First request database ID")
    compare_parser.add_argument("id_b", type=int, help="Second request database ID")

    args = parser.parse_args()
    setup_logging(args.verbose)

    redact_keys_list = [k.strip() for k in args.redact_keys.split(",") if k.strip()]

    if args.command == "start":
        start_server(
            args.host,
            args.port,
            args.db_path,
            args.sig_header,
            args.sig_secret,
            args.sig_style,
        )
    elif args.command == "list":
        list_requests(args.db_path)
    elif args.command == "show":
        show_request(args.db_path, args.id, redact_keys_list)
    elif args.command == "replay":
        replay_request(args.db_path, args.id, args.target_url, redact_keys_list)
    elif args.command == "compare":
        compare_requests(args.db_path, args.id_a, args.id_b, redact_keys_list)


if __name__ == "__main__":
    main()
