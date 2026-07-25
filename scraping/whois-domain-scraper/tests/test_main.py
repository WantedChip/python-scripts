"""Unit tests for WHOIS domain scraper."""

import unittest
from unittest.mock import patch

from main import (
    WhoisInfo,
    calculate_days_until_expiry,
    format_table,
    lookup_domain,
    parse_rdap_response,
    parse_whois_text,
)


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


if __name__ == "__main__":
    unittest.main()
