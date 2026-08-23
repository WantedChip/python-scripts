"""Unit tests for WHOIS domain scraper."""

import contextlib
import io
import json
import os
import socket
import tempfile
import unittest
import urllib.error
from typing import Any, List
from unittest.mock import MagicMock, patch

from main import (
    WhoisInfo,
    build_parser,
    calculate_days_until_expiry,
    format_table,
    lookup_domain,
    main,
    parse_rdap_response,
    parse_whois_text,
    query_rdap,
    query_whois_socket,
)


def _urlopen_result(payload: Any, status: int = 200) -> MagicMock:
    """Build a mock urlopen return value usable as a context manager."""
    resp = MagicMock()
    resp.status = status
    body = payload if isinstance(payload, str) else json.dumps(payload)
    resp.read.return_value = body.encode("utf-8")
    resp.__enter__.return_value = resp
    return resp


class TestWhoisDomainScraper(unittest.TestCase):

    def test_calculate_days_until_expiry(self):
        # Invalid / empty
        self.assertIsNone(calculate_days_until_expiry(None))
        self.assertIsNone(calculate_days_until_expiry("invalid date format"))

        # Valid ISO string format
        expiry_iso = "2099-12-31T23:59:59Z"
        days = calculate_days_until_expiry(expiry_iso)
        self.assertIsNotNone(days)
        self.assertGreater(days, 0)

    def test_parse_rdap_response(self):
        sample_rdap = {
            "entities": [
                {
                    "roles": ["registrar"],
                    "vcardArray": [
                        "vcard",
                        [
                            ["version", {}, "text", "4.0"],
                            ["fn", {}, "text", "Example Registrar LLC"],
                        ],
                    ],
                }
            ],
            "events": [
                {"eventAction": "registration", "eventDate": "2020-01-15T10:00:00Z"},
                {"eventAction": "expiration", "eventDate": "2028-01-15T10:00:00Z"},
            ],
            "nameservers": [
                {"ldhName": "NS1.EXAMPLE.COM"},
                {"ldhName": "NS2.EXAMPLE.COM"},
            ],
            "status": ["active", "clientTransferProhibited"],
        }

        info = parse_rdap_response("example.com", sample_rdap)
        self.assertEqual(info.domain, "example.com")
        self.assertEqual(info.registrar, "Example Registrar LLC")
        self.assertEqual(info.creation_date, "2020-01-15T10:00:00Z")
        self.assertEqual(info.expiration_date, "2028-01-15T10:00:00Z")
        self.assertIn("ns1.example.com", info.name_servers)
        self.assertIn("active", info.status)
        self.assertEqual(info.query_source, "RDAP")

    def test_parse_whois_text(self):
        raw_text = """
Domain Name: testdomain.org
Registrar: Global Registrar Inc.
Creation Date: 2021-05-10T12:00:00Z
Registry Expiry Date: 2029-05-10T12:00:00Z
Name Server: ns1.testdomain.org
Name Server: ns2.testdomain.org
Domain Status: clientTransferProhibited https://icann.org/epp#clientTransferProhibited
"""

        info = parse_whois_text("testdomain.org", raw_text)
        self.assertEqual(info.domain, "testdomain.org")
        self.assertEqual(info.registrar, "Global Registrar Inc.")
        self.assertEqual(info.creation_date, "2021-05-10T12:00:00Z")
        self.assertEqual(info.expiration_date, "2029-05-10T12:00:00Z")
        self.assertIn("ns1.testdomain.org", info.name_servers)
        self.assertEqual(info.query_source, "WHOIS_SOCKET")

    def test_format_table(self):
        info1 = WhoisInfo(
            domain="domain1.com",
            registrar="Registrar A",
            expiration_date="2027-01-01",
            days_until_expiry=500,
            status=["ok"],
        )
        table_output = format_table([info1])
        self.assertIn("domain1.com", table_output)
        self.assertIn("Registrar A", table_output)
        self.assertIn("500", table_output)

    @patch("main.query_rdap")
    def test_lookup_domain(self, mock_query_rdap):
        mock_query_rdap.return_value = {
            "entities": [],
            "events": [
                {"eventAction": "expiration", "eventDate": "2030-01-01T00:00:00Z"}
            ],
            "nameservers": [],
            "status": [],
        }
        info = lookup_domain("mockdomain.com")
        self.assertEqual(info.domain, "mockdomain.com")
        self.assertEqual(info.expiration_date, "2030-01-01T00:00:00Z")


class TestCalculateDaysUntil_expiry(unittest.TestCase):
    """Date parsing variants used for expiry computation."""

    def test_supported_date_formats(self) -> None:
        for value in (
            "2030-01-01T00:00:00Z",
            "2030-01-01T00:00:00.123456Z",
            "2030-01-01T00:00:00+02:00",
            "2030-01-01 00:00:00",
            "2030-01-01",
            "01-Jan-2030",
        ):
            with self.subTest(value=value):
                self.assertGreater(
                    calculate_days_until_expiry(value) or -1,
                    0,
                )

    def test_regex_fallback_extracts_embedded_date(self) -> None:
        days = calculate_days_until_expiry("expires 2030-06-15 sometime")
        self.assertIsNotNone(days)

    def test_unparseable_date_returns_none(self) -> None:
        self.assertIsNone(calculate_days_until_expiry("13-45-9999"))
        self.assertIsNone(calculate_days_until_expiry(""))


class TestQueryRdap(unittest.TestCase):
    """RDAP HTTP client with mocked urlopen."""

    RDAP_OK = {"handle": "EXAMPLE-COM", "ldhName": "example.com"}

    def test_query_success_returns_parsed_dict(self) -> None:
        with patch(
            "main.urllib.request.urlopen", return_value=_urlopen_result(self.RDAP_OK)
        ) as mock_open:
            data = query_rdap("Example.COM ")
        self.assertEqual(data, self.RDAP_OK)
        url = mock_open.call_args.args[0].full_url
        self.assertEqual(url, "https://rdap.org/domain/example.com")

    def test_query_non_200_returns_none(self) -> None:
        resp = _urlopen_result(self.RDAP_OK, status=404)
        with patch("main.urllib.request.urlopen", return_value=resp):
            self.assertIsNone(query_rdap("example.com"))

    def test_query_network_error_returns_none(self) -> None:
        with patch(
            "main.urllib.request.urlopen",
            side_effect=urllib.error.URLError("offline"),
        ):
            self.assertIsNone(query_rdap("example.com"))

    def test_query_invalid_json_returns_none(self) -> None:
        resp = _urlopen_result("<html>gateway error</html>")
        with patch("main.urllib.request.urlopen", return_value=resp):
            self.assertIsNone(query_rdap("example.com"))

    def test_query_non_dict_json_returns_none(self) -> None:
        resp = _urlopen_result(["not", "a", "dict"])
        with patch("main.urllib.request.urlopen", return_value=resp):
            self.assertIsNone(query_rdap("example.com"))


class TestParseRdapResponseRegistrar(unittest.TestCase):
    """Registrar extraction fallbacks."""

    def test_registrar_handle_used_when_vcard_missing(self) -> None:
        rdap = {"entities": [{"roles": ["registrar"], "handle": "REG-1234"}]}
        info = parse_rdap_response("example.com", rdap)
        self.assertEqual(info.registrar, "REG-1234")

    def test_days_until_expiry_computed_from_events(self) -> None:
        rdap = {
            "events": [
                {"eventAction": "expiration", "eventDate": "2099-01-01T00:00:00Z"}
            ]
        }
        info = parse_rdap_response("example.com", rdap)
        self.assertIsNotNone(info.days_until_expiry)
        assert info.days_until_expiry is not None
        self.assertGreater(info.days_until_expiry, 365)

    def test_to_dict_shape(self) -> None:
        info = WhoisInfo(domain="d.com")
        as_dict = info.to_dict()
        self.assertEqual(as_dict["query_source"], "RDAP")
        self.assertEqual(as_dict["name_servers"], [])


class TestQueryWhoisSocket(unittest.TestCase):
    """Raw TCP WHOIS query against a mocked socket."""

    def _mock_socket(self, chunks: List[bytes]) -> MagicMock:
        sock = MagicMock()
        sock.recv.side_effect = chunks + [b""]
        return sock

    def test_successful_query_collects_full_response(self) -> None:
        sock = self._mock_socket([b"Domain Name: EXAMPLE", b".COM\r\n"])
        with patch("main.socket.socket", return_value=sock):
            result = query_whois_socket("example.com", "whois.example.net")
        self.assertIn("Domain Name: EXAMPLE.COM", result)
        sock.sendall.assert_called_once_with(b"example.com\r\n")
        sock.connect.assert_called_once_with(("whois.example.net", 43))
        sock.close.assert_called()

    def test_socket_error_returns_empty_string(self) -> None:
        sock = MagicMock()
        sock.connect.side_effect = socket.error("refused")
        with patch("main.socket.socket", return_value=sock):
            self.assertEqual(query_whois_socket("example.com"), "")
            sock.close.assert_called()


class TestLookupDomainFallback(unittest.TestCase):
    """lookup_domain socket-fallback orchestration."""

    RAW_WHOIS = (
        "Domain Name: FALLBACK.ORG\n"
        "Registrar: Fallback Registrar LLC\n"
        "Registry Expiry Date: 2029-09-09T00:00:00Z\n"
        "Name Server: NS1.FALLBACK.ORG\n"
    )

    @patch("main.query_whois_socket")
    @patch("main.query_rdap")
    def test_rdap_failure_falls_back_via_iana_refer(
        self, mock_rdap: MagicMock, mock_sock: MagicMock
    ) -> None:
        mock_rdap.return_value = None
        mock_sock.side_effect = [
            "refer: whois.pir.org\n% IANA whois server",
            self.RAW_WHOIS,
        ]
        info = lookup_domain("fallback.org")
        self.assertEqual(info.query_source, "WHOIS_SOCKET")
        self.assertEqual(info.registrar, "Fallback Registrar LLC")
        self.assertEqual(mock_sock.call_args_list[1].args[1], "whois.pir.org")

    @patch("main.query_whois_socket")
    @patch("main.query_rdap")
    def test_empty_socket_responses_yield_failed_info(
        self, mock_rdap: MagicMock, mock_sock: MagicMock
    ) -> None:
        mock_rdap.return_value = None
        mock_sock.return_value = ""
        info = lookup_domain("unknown-domain.xyz")
        self.assertEqual(info.query_source, "FAILED")
        self.assertEqual(info.domain, "unknown-domain.xyz")


class TestFormatTable(unittest.TestCase):
    """Table rendering edge cases."""

    def test_missing_fields_render_placeholders(self) -> None:
        info = WhoisInfo(domain="bare-domain.io")
        table = format_table([info])
        self.assertIn("Unknown", table)
        self.assertIn("N/A", table)


class TestWhoisCli(unittest.TestCase):
    """CLI-level tests for build_parser and main()."""

    INFO = WhoisInfo(
        domain="cli-example.com",
        registrar="CLI Registrar",
        expiration_date="2029-03-03T00:00:00Z",
        days_until_expiry=900,
        status=["ok"],
    )

    def test_build_parser_defaults(self) -> None:
        args = build_parser().parse_args(["--domain", "x.com"])
        self.assertEqual(args.format, "table")
        self.assertIsNone(args.output)
        self.assertIsNone(args.file)

    def _run_main(self, argv: List[str]) -> tuple:
        """Run main() capturing stdout/stderr; return (code, out, err)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_main_single_domain_table_output(self) -> None:
        with patch("main.lookup_domain", return_value=self.INFO) as mock_lookup:
            code, out, _ = self._run_main(["--domain", "CLI-Example.COM"])
        self.assertEqual(code, 0)
        mock_lookup.assert_called_once_with("CLI-Example.COM")
        self.assertIn("Domain", out)
        self.assertIn("cli-example.com", out)
        self.assertIn("CLI Registrar", out)

    def test_main_json_output_written_to_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "whois.json")
            argv = ["--domain", "cli-example.com", "--format", "json", "-o", out_path]
            with patch("main.lookup_domain", return_value=self.INFO):
                code, out, _ = self._run_main(argv)
            self.assertEqual(code, 0)
            self.assertIn(f"Results saved to {out_path}", out)
            with open(out_path, encoding="utf-8") as f:
                saved: Any = json.load(f)
            self.assertEqual(saved[0]["domain"], "cli-example.com")
            self.assertEqual(saved[0]["registrar"], "CLI Registrar")

    def test_main_reads_domain_list_file_with_comments(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            list_path = os.path.join(tmpdir, "domains.txt")
            with open(list_path, "w", encoding="utf-8") as f:
                f.write("# comment line\n\na.example\nb.example\n")
            with patch("main.lookup_domain", return_value=self.INFO) as mock_lu:
                code, _, _ = self._run_main(["--file", list_path])
        self.assertEqual(code, 0)
        self.assertEqual(mock_lu.call_count, 2)

    def test_main_unreadable_file_returns_exit_code_one(self) -> None:
        missing = os.path.join("does", "not", "exist", "domains.txt")
        code, _, err = self._run_main(["--file", missing])
        self.assertEqual(code, 1)
        self.assertIn("Error reading file", err)

    def test_main_without_source_prints_help_and_fails(self) -> None:
        code, out, _ = self._run_main([])
        self.assertEqual(code, 1)
        self.assertIn("usage:", out.lower())


if __name__ == "__main__":
    unittest.main()
