#!/usr/bin/env python3
"""Reverse proxy API traffic recorder.

Records development API traffic, sanitizes sensitive fields, and saves
deterministic mocks.
"""

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Tuple
from urllib.parse import urljoin, urlparse


def sanitize_dict(data: Any, sanitize_keys: List[str]) -> Any:
    """Recursively redact sensitive keys in a dictionary or list."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if any(s.lower() == k.lower() for s in sanitize_keys):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_dict(v, sanitize_keys)
        return sanitized
    if isinstance(data, list):
        return [sanitize_dict(item, sanitize_keys) for item in data]
    return data


def get_mock_filename(method: str, path: str, query: str) -> str:
    """Generate a deterministic and filesystem-friendly mock filename."""
    clean_path = path.strip("/").replace("/", "_").replace("-", "_")
    if not clean_path:
        clean_path = "root"

    query_hash = ""
    if query:
        query_hash = (
            "_"
            + hashlib.md5(query.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
        )

    return f"{method.lower()}_{clean_path}{query_hash}.json"


class TrafficRecorderHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler that proxies requests and records traffic."""

    target_url: str
    output_dir: str
    sanitize_keys: List[str]
    verbose: bool

    # pylint: disable=redefined-builtin
    def log_message(self, format: str, *args: Any) -> None:
        """Suppress standard logging unless verbose mode is enabled."""
        if self.verbose:
            date_str = self.log_date_time_string()
            formatted_args = format % args
            msg = f"{self.address_string()} - - [{date_str}] {formatted_args}\n"
            sys.stderr.write(msg)

    def do_request(self) -> None:
        """Process incoming requests, proxy them, sanitize, and record."""
        content_length = int(self.headers.get("Content-Length", 0))
        req_body = self.rfile.read(content_length) if content_length > 0 else b""

        parsed_target = urlparse(self.target_url)
        target_path_query = self.path
        full_target_url = urljoin(self.target_url, target_path_query)

        if self.verbose:
            print(f"Proxying: {self.command} {target_path_query} -> {full_target_url}")

        req_headers: Dict[str, str] = {}
        for k, v in self.headers.items():
            if k.lower() == "host":
                req_headers[k] = parsed_target.netloc
            else:
                req_headers[k] = v

        req = urllib.request.Request(
            full_target_url,
            data=req_body if req_body else None,
            headers=req_headers,
            method=self.command,
        )

        resp_status = 500
        resp_headers: List[Tuple[str, str]] = []
        resp_body = b""

        try:
            with urllib.request.urlopen(req) as response:  # nosec B310
                resp_status = response.status
                resp_headers = response.getheaders()
                resp_body = response.read()
        except urllib.error.HTTPError as e:
            resp_status = e.code
            resp_headers = e.headers.items()
            resp_body = e.read()
        except (OSError, urllib.error.URLError) as e:
            print(f"Failed to proxy request: {e}", file=sys.stderr)
            self.send_response(502)
            self.end_headers()
            self.wfile.write(f"Bad Gateway: {e}".encode("utf-8"))
            return

        self.send_response(resp_status)
        for k, v in resp_headers:
            if k.lower() != "content-length":
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(resp_body)

        self.record_traffic(
            target_path_query, req_body, resp_status, resp_headers, resp_body
        )

    # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    def record_traffic(
        self,
        path_query: str,
        req_body: bytes,
        resp_status: int,
        resp_headers: List[Tuple[str, str]],
        resp_body: bytes,
    ) -> None:
        """Sanitize and write recorded transaction into output directory."""
        parsed = urlparse(path_query)
        path = parsed.path
        query = parsed.query

        req_headers_dict = dict(self.headers.items())
        sanitized_req_headers = sanitize_dict(req_headers_dict, self.sanitize_keys)

        sanitized_resp_headers = {}
        for k, v in resp_headers:
            sanitized_resp_headers[k] = v
        sanitized_resp_headers = sanitize_dict(
            sanitized_resp_headers, self.sanitize_keys
        )

        req_json: Any = None
        if req_body:
            try:
                req_json = json.loads(req_body.decode("utf-8"))
                req_json = sanitize_dict(req_json, self.sanitize_keys)
            except (UnicodeDecodeError, json.JSONDecodeError):
                req_json = req_body.decode("utf-8", errors="replace")

        resp_json: Any = None
        if resp_body:
            try:
                resp_json = json.loads(resp_body.decode("utf-8"))
                resp_json = sanitize_dict(resp_json, self.sanitize_keys)
            except (UnicodeDecodeError, json.JSONDecodeError):
                resp_json = resp_body.decode("utf-8", errors="replace")

        record = {
            "request": {
                "method": self.command,
                "path": path,
                "query": query,
                "headers": sanitized_req_headers,
                "body": req_json,
            },
            "response": {
                "status_code": resp_status,
                "headers": sanitized_resp_headers,
                "body": resp_json,
            },
        }

        filename = get_mock_filename(self.command, path, query)
        filepath = os.path.join(self.output_dir, filename)

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=4)
            print(f"Recorded transaction: {self.command} {path} -> {filename}")
        except OSError as e:
            print(f"Error saving mock file: {e}", file=sys.stderr)

    # pylint: disable=invalid-name,missing-function-docstring
    def do_GET(self) -> None:
        self.do_request()

    def do_POST(self) -> None:
        self.do_request()

    def do_PUT(self) -> None:
        self.do_request()

    def do_DELETE(self) -> None:
        self.do_request()

    def do_PATCH(self) -> None:
        self.do_request()

    def do_OPTIONS(self) -> None:
        self.do_request()

    def do_HEAD(self) -> None:
        self.do_request()


def write_mock_driver(output_dir: str) -> None:
    """Generate a Python mock helper module to load mocks in tests."""
    driver_code = """# Generated Mock Driver helper.
# This utility matches incoming request parameters against local JSON mocks.

import json
import os
import hashlib
from typing import Optional, Dict, Any

MOCKS_DIR = os.path.dirname(os.path.abspath(__file__))

def get_mock_filename(method: str, path: str, query: str = "") -> str:
    clean_path = path.strip("/").replace("/", "_").replace("-", "_")
    if not clean_path:
        clean_path = "root"
    query_hash = ""
    if query:
        md5_hex = hashlib.md5(
            query.encode("utf-8"), usedforsecurity=False
        ).hexdigest()[:8]
        query_hash = f"_{md5_hex}"
    return f"{method.lower()}_{clean_path}{query_hash}.json"

def load_mock(method: str, path: str, query: str = "") -> Optional[Dict[str, Any]]:
    \"\"\"Finds and returns the recorded response mock for the request.\"\"\"
    filename = get_mock_filename(method, path, query)
    filepath = os.path.join(MOCKS_DIR, filename)
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return None
"""
    filepath = os.path.join(output_dir, "mock_driver.py")
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(driver_code)
        print(f"Generated mock driver helper at {filepath}")
    except OSError as e:
        print(f"Error creating mock driver helper: {e}", file=sys.stderr)


def main() -> None:
    """CLI Entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Record your application's development API traffic to "
            "local mock JSON responses."
        )
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=8080,
        help="Local port to run the recording proxy server (default: 8080).",
    )
    parser.add_argument(
        "-t",
        "--target",
        required=True,
        help=(
            "The actual target API host to proxy requests to "
            "(e.g. https://api.github.com)."
        ),
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default="mocks",
        help="Directory to save mock response JSON files (default: mocks).",
    )
    parser.add_argument(
        "-s",
        "--sanitize",
        default="Authorization,Cookie,api_key,token,password,secret",
        help="Comma-separated header or body keys to redact/sanitize.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output log."
    )

    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    sanitize_keys = [k.strip() for k in args.sanitize.split(",") if k.strip()]

    target_url = args.target
    if not target_url.startswith(("http://", "https://")):
        target_url = "https://" + target_url

    write_mock_driver(args.output_dir)

    _target_url = target_url
    _sanitize_keys = sanitize_keys

    # pylint: disable=missing-class-docstring
    class ConfiguredHandler(TrafficRecorderHandler):
        target_url = _target_url
        output_dir = args.output_dir
        sanitize_keys = _sanitize_keys
        verbose = args.verbose

    print(f"Starting API Recorder Proxy on http://localhost:{args.port}")
    print(f"Proxying requests to: {target_url}")
    print(f"Redacting fields: {', '.join(sanitize_keys)}")
    print(f"Saving mock JSONs to directory: {args.output_dir}")
    print("Press Ctrl+C to stop.")

    server = ThreadingHTTPServer(("localhost", args.port), ConfiguredHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping API Recorder Proxy server.")
        sys.exit(0)


if __name__ == "__main__":
    main()
