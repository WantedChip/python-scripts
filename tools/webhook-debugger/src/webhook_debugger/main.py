"""Webhook Debugging Server — local webhook receiver, inspector, and replay tool."""

import argparse
import difflib
import http.server
import json
import logging
import sqlite3
import sys
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("webhook_debugger")


def setup_logging(verbose: bool) -> None:
    """Configure console logging based on verbosity level."""
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
        """Initialize the SQLite database and create schemas if needed."""
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._create_table()

    def _create_table(self) -> None:
        """Create the request log table."""
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    headers TEXT NOT NULL,
                    body TEXT NOT NULL
                )
                """
            )

    def insert_request(
        self, method: str, path: str, headers: Dict[str, str], body: str
    ) -> int:
        """Insert a logged request and return its generated ID."""
        now = datetime.now().isoformat()
        headers_str = json.dumps(headers)
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO requests (timestamp, method, path, headers, body)
                VALUES (?, ?, ?, ?, ?)
                """,
                (now, method, path, headers_str, body),
            )
            row_id = cursor.lastrowid
            if row_id is None:
                raise sqlite3.DatabaseError("Failed to retrieve inserted row ID.")
            return int(row_id)

    def get_requests(self) -> List[Dict[str, Any]]:
        """Retrieve all logged requests from the database."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, timestamp, method, path, headers, body "
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
                }
            )
        return requests

    def get_request(self, req_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve a specific request by ID."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, timestamp, method, path, headers, body "
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
        }

    def close(self) -> None:
        """Close SQLite database connection."""
        self.conn.close()


class WebhookHTTPHandler(http.server.BaseHTTPRequestHandler):
    """HTTP Request Handler that records details to the database."""

    def log_message(self, format_str: str, *args: Any) -> None:
        """Silence standard server log output to delegate to logging module."""
        # pylint: disable=arguments-differ
        logger.debug(format_str, *args)

    def do_request(self) -> None:
        """Read body, save request metadata, and respond 200 OK."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = ""
        if content_length > 0:
            try:
                body = self.rfile.read(content_length).decode("utf-8")
            except OSError as e:
                logger.error("Failed to read request body: %s", e)

        headers_dict = dict(self.headers.items())
        server_instance: Any = self.server
        db: WebhookDatabase = server_instance.db

        req_id = db.insert_request(self.command, self.path, headers_dict, body)
        logger.info(
            "Received Webhook [ID: %d] %s %s from %s",
            req_id,
            self.command,
            self.path,
            self.client_address[0],
        )

        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {"status": "ok", "request_id": req_id}
            self.wfile.write(json.dumps(response).encode("utf-8"))
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
    """Custom HTTPServer holding the database reference."""

    def __init__(self, server_address: Tuple[str, int], db: WebhookDatabase) -> None:
        """Initialize server with custom DB reference."""
        self.db = db
        super().__init__(server_address, WebhookHTTPHandler)


def start_server(host: str, port: int, db_path: str) -> None:
    """Launch the webhook debugger web server."""
    db = WebhookDatabase(db_path)
    server = WebhookServer((host, port), db)
    logger.info("Starting Webhook Debugging Server on %s:%d ...", host, port)
    logger.info("Archiving requests to database: %s", db_path)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down Webhook Debugging Server.")
    finally:
        server.server_close()
        db.close()


def list_requests(db_path: str) -> None:
    """List captured requests from SQLite archive."""
    db = WebhookDatabase(db_path)
    requests = db.get_requests()
    db.close()

    if not requests:
        logger.info("No captured webhook requests found in database.")
        return

    print(f"{'ID':<5} | {'TIMESTAMP':<25} | {'METHOD':<8} | {'PATH':<30}")
    print("-" * 75)
    for r in requests:
        path = r["path"]
        if len(path) > 27:
            path = path[:24] + "..."
        print(f"{r['id']:<5} | {r['timestamp']:<25} | {r['method']:<8} | {path:<30}")
    print("-" * 75)


def show_request(db_path: str, req_id: int) -> None:
    """Display headers and payload for a specific request ID."""
    db = WebhookDatabase(db_path)
    r = db.get_request(req_id)
    db.close()

    if not r:
        logger.error("Request ID %d not found in database.", req_id)
        sys.exit(1)

    print(f"Request ID: {r['id']}")
    print(f"Timestamp : {r['timestamp']}")
    print(f"Method    : {r['method']}")
    print(f"Path      : {r['path']}")
    print("\nHeaders:")
    for k, v in r["headers"].items():
        print(f"  {k}: {v}")
    print("\nBody:")
    body = r["body"]
    if not body:
        print("  (Empty Body)")
    else:
        try:
            # Pretty-print JSON if possible
            parsed_json = json.loads(body)
            print(json.dumps(parsed_json, indent=2))
        except ValueError:
            print(body)


def replay_request(db_path: str, req_id: int, target_url: str) -> None:
    """Replay request headers and payload to another endpoint."""
    db = WebhookDatabase(db_path)
    r = db.get_request(req_id)
    db.close()

    if not r:
        logger.error("Request ID %d not found in database.", req_id)
        sys.exit(1)

    logger.info("Replaying request ID %d to URL %s ...", req_id, target_url)

    # Exclude system/host headers that get populated automatically
    exclude_headers = {"host", "connection", "content-length"}
    headers = {
        k: v for k, v in r["headers"].items() if k.lower() not in exclude_headers
    }

    body_bytes = r["body"].encode("utf-8") if r["body"] else b""

    # Prepare HTTP Request
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
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Failed to replay request: %s", e)
        sys.exit(1)


def compare_requests(db_path: str, req_id_a: int, req_id_b: int) -> None:
    """Diff the headers and body of two captured requests."""
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

    # Format Request A
    lines_a = [
        f"Method: {req_a['method']}",
        f"Path: {req_a['path']}",
        "Headers:",
    ]
    for k, v in sorted(req_a["headers"].items()):
        lines_a.append(f"  {k}: {v}")
    lines_a.append("Body:")
    body_a = req_a["body"]
    try:
        body_a = json.dumps(json.loads(body_a), indent=2)
    except ValueError:
        pass
    lines_a.extend(body_a.splitlines())

    # Format Request B
    lines_b = [
        f"Method: {req_b['method']}",
        f"Path: {req_b['path']}",
        "Headers:",
    ]
    for k, v in sorted(req_b["headers"].items()):
        lines_b.append(f"  {k}: {v}")
    lines_b.append("Body:")
    body_b = req_b["body"]
    try:
        body_b = json.dumps(json.loads(body_b), indent=2)
    except ValueError:
        pass
    lines_b.extend(body_b.splitlines())

    # Generate Diff
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
    """CLI entry point for Webhook Debugging Server."""
    parser = argparse.ArgumentParser(
        description=(
            "Receive webhooks locally, inspect headers/payloads, "
            "replay requests, and compare deliveries."
        )
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="webhook_debug.db",
        help=("Path to SQLite archive database file " "(default: webhook_debug.db)"),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable detailed log descriptions",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # start subcommand
    start_parser = subparsers.add_parser(
        "start", help="Start the local webhook debugging server"
    )
    start_parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Hostname or IP address to bind to (default: 127.0.0.1)",
    )
    start_parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="TCP port to listen on (default: 8080)",
    )

    # list subcommand
    subparsers.add_parser("list", help="List all received requests")

    # show subcommand
    show_parser = subparsers.add_parser(
        "show", help="Display details of a specific request"
    )
    show_parser.add_argument(
        "id", type=int, help="ID of the captured request to display"
    )

    # replay subcommand
    replay_parser = subparsers.add_parser(
        "replay", help="Replay a captured request to a target HTTP endpoint"
    )
    replay_parser.add_argument(
        "id", type=int, help="ID of the captured request to replay"
    )
    replay_parser.add_argument(
        "--to",
        dest="target_url",
        type=str,
        required=True,
        help="Target HTTP endpoint URL to forward to",
    )

    # compare subcommand
    compare_parser = subparsers.add_parser(
        "compare", help="Diff the headers and body of two requests"
    )
    compare_parser.add_argument("id_a", type=int, help="ID of the first request")
    compare_parser.add_argument("id_b", type=int, help="ID of the second request")

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.command == "start":
        start_server(args.host, args.port, args.db_path)
    elif args.command == "list":
        list_requests(args.db_path)
    elif args.command == "show":
        show_request(args.db_path, args.id)
    elif args.command == "replay":
        replay_request(args.db_path, args.id, args.target_url)
    elif args.command == "compare":
        compare_requests(args.db_path, args.id_a, args.id_b)


if __name__ == "__main__":
    main()
