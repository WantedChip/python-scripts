"""Unit tests for University Search Fetcher."""

import csv
import io
import json
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from main import (
    export_csv,
    export_json,
    extract_university_details,
    fetch_json,
    format_university_table,
    main,
    search_universities,
)


class TestUniversitySearchFetcher(unittest.TestCase):
    """Test suite for university search fetcher functions."""

    def setUp(self) -> None:
        self.raw_uni = {
            "name": "University of Toronto",
            "country": "Canada",
            "alpha_two_code": "CA",
            "state-province": "Ontario",
            "web_pages": ["http://www.utoronto.ca/"],
            "domains": ["utoronto.ca"],
        }

    def test_extract_university_details(self) -> None:
        """Test extracting formatted fields from raw university record."""
        details = extract_university_details(self.raw_uni)
        self.assertEqual(details["name"], "University of Toronto")
        self.assertEqual(details["country"], "Canada")
        self.assertEqual(details["primary_website"], "http://www.utoronto.ca/")
        self.assertEqual(details["primary_domain"], "utoronto.ca")
        self.assertEqual(details["state_province"], "Ontario")

    def test_format_university_table(self) -> None:
        """Test formatting university results into a terminal table."""
        details = extract_university_details(self.raw_uni)
        table = format_university_table([details], limit=5)
        self.assertIn("University of Toronto", table)
        self.assertIn("Canada", table)
        self.assertIn("http://www.utoronto.ca/", table)

    @patch("main.fetch_json")
    def test_search_universities(self, mock_fetch: MagicMock) -> None:
        """Test API query building for search request."""
        mock_fetch.return_value = [self.raw_uni]
        results = search_universities(country="Canada", name="Toronto")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "University of Toronto")

    def test_export_json(self) -> None:
        """Test exporting search records to JSON file."""
        details = extract_university_details(self.raw_uni)
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = str(Path(tmpdir) / "unis.json")
            success = export_json([details], file_path)
            self.assertTrue(success)
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["name"], "University of Toronto")

    def test_export_csv(self) -> None:
        """Test exporting search records to CSV file."""
        details = extract_university_details(self.raw_uni)
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = str(Path(tmpdir) / "unis.csv")
            success = export_csv([details], file_path)
            self.assertTrue(success)
            with open(file_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["name"], "University of Toronto")

    def test_export_json_oserror(self) -> None:
        """Unwritable JSON targets report failure instead of crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = str(Path(tmpdir) / "missing" / "unis.json")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                success = export_json(
                    [extract_university_details(self.raw_uni)], bad_path
                )
        self.assertFalse(success)
        self.assertIn("Error exporting JSON", stderr.getvalue())

    def test_export_csv_empty_list(self) -> None:
        """Exporting an empty record list is rejected up front."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = str(Path(tmpdir) / "unis.csv")
            self.assertFalse(export_csv([], file_path))
            self.assertFalse(Path(file_path).exists())

    def test_export_csv_oserror(self) -> None:
        """Unwritable CSV targets report failure instead of crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = str(Path(tmpdir) / "missing" / "unis.csv")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                success = export_csv(
                    [extract_university_details(self.raw_uni)], bad_path
                )
        self.assertFalse(success)
        self.assertIn("Error exporting CSV", stderr.getvalue())


class TestNetworkLayer(unittest.TestCase):
    """Tests for the low-level Hipolabs HTTP helper."""

    @patch("main.urllib.request.urlopen")
    def test_fetch_json_success(self, mock_urlopen: MagicMock) -> None:
        """A 200 response with valid JSON is parsed and returned."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'[{"name": "MIT"}]'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = fetch_json("http://universities.hipolabs.com/search?x=1")
        self.assertEqual(result, [{"name": "MIT"}])

    @patch("main.urllib.request.urlopen")
    def test_fetch_json_non_200_returns_none(self, mock_urlopen: MagicMock) -> None:
        """Non-200 status codes yield None without raising."""
        mock_resp = MagicMock()
        mock_resp.status = 502
        mock_resp.read.return_value = b"bad gateway"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        self.assertIsNone(fetch_json("http://universities.hipolabs.com/search"))

    @patch("main.urllib.request.urlopen")
    def test_fetch_json_url_error_returns_none(self, mock_urlopen: MagicMock) -> None:
        """Connection failures are reported and mapped to None."""
        mock_urlopen.side_effect = urllib.error.URLError("connection refused")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = fetch_json("http://universities.hipolabs.com/search")
        self.assertIsNone(result)
        self.assertIn(
            "Error requesting http://universities.hipolabs.com/search",
            stderr.getvalue(),
        )

    @patch("main.urllib.request.urlopen")
    def test_fetch_json_malformed_payload_returns_none(
        self, mock_urlopen: MagicMock
    ) -> None:
        """Invalid JSON payloads are treated as fetch failures."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"{{not-json"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        self.assertIsNone(fetch_json("http://universities.hipolabs.com/search"))


class TestSearchBehaviour(unittest.TestCase):
    """Tests for query building and error mapping in search_universities."""

    @patch("main.fetch_json")
    def test_network_failure_raises_runtime_error(self, mock_fetch: MagicMock) -> None:
        """A failed fetch is surfaced as RuntimeError to the CLI."""
        mock_fetch.return_value = None
        with self.assertRaisesRegex(RuntimeError, "Network error"):
            search_universities(country="Canada")

    @patch("main.fetch_json")
    def test_no_filters_builds_empty_query(self, mock_fetch: MagicMock) -> None:
        """Blank filters produce a bare endpoint URL."""
        mock_fetch.return_value = []
        search_universities(country="  ", name=None)
        url = mock_fetch.call_args[0][0]
        self.assertTrue(url.endswith("/search?"))

    @patch("main.fetch_json")
    def test_name_filter_builds_query(self, mock_fetch: MagicMock) -> None:
        """Name-only searches encode the keyword parameter."""
        mock_fetch.return_value = []
        search_universities(name="Oxford")
        self.assertIn("name=Oxford", mock_fetch.call_args[0][0])


class TestTableFormatting(unittest.TestCase):
    """Tests for terminal table rendering."""

    def test_empty_table_message(self) -> None:
        """No records render an explicit empty-state message."""
        self.assertEqual(format_university_table([]), "No results to display.")

    def test_long_names_are_truncated(self) -> None:
        """Names longer than the column width are truncated with '..'."""
        details = extract_university_details(
            {
                "name": "L" * 60,
                "country": "Testland",
                "web_pages": ["http://l.example"],
                "domains": ["l.example"],
            }
        )
        table = format_university_table([details], limit=5)
        self.assertIn(("L" * 38 + ".."), table)


class TestCli(unittest.TestCase):
    """CLI-level tests covering main() flows via sys.argv."""

    def setUp(self) -> None:
        self.raw_uni = {
            "name": "University of Toronto",
            "country": "Canada",
            "alpha_two_code": "CA",
            "state-province": "Ontario",
            "web_pages": ["http://www.utoronto.ca/"],
            "domains": ["utoronto.ca"],
        }

    def _run_cli(self, *args: str) -> Any:
        """Run main() with patched argv; capture streams and exit code."""
        stdout, stderr = io.StringIO(), io.StringIO()
        exit_code: Any = None
        argv = ["main.py"] + list(args)
        with redirect_stdout(stdout), redirect_stderr(stderr), patch("sys.argv", argv):
            try:
                main()
            except SystemExit as exc:
                exit_code = exc.code
        return stdout.getvalue(), stderr.getvalue(), exit_code

    @patch("main.search_universities")
    def test_cli_search_and_table(self, mock_search: MagicMock) -> None:
        """A filtered search prints the results table."""
        mock_search.return_value = [
            {
                "name": "University of Toronto",
                "country": "Canada",
                "alpha_two_code": "CA",
                "state-province": "Ontario",
                "web_pages": ["http://www.utoronto.ca/"],
                "domains": ["utoronto.ca"],
            }
        ]
        stdout, _, code = self._run_cli("--country", "Canada", "--limit", "5")
        self.assertIsNone(code)
        self.assertIn("UNIVERSITY SEARCH RESULTS (Showing 1 of 1)", stdout)
        self.assertIn("University of Toronto", stdout)

    def test_cli_requires_a_filter(self) -> None:
        """Running without --country/--name fails argument validation."""
        _, stderr, code = self._run_cli()
        self.assertEqual(code, 2)
        self.assertIn("At least one search filter", stderr)

    @patch("main.search_universities")
    def test_cli_no_results_exits_one(self, mock_search: MagicMock) -> None:
        """Empty result sets exit 1 with an error on stderr."""
        mock_search.return_value = []
        _, stderr, code = self._run_cli("--name", "zzz-nope-university")
        self.assertEqual(code, 1)
        self.assertIn("No matching universities found.", stderr)

    @patch("main.search_universities")
    def test_cli_exports_json_and_csv(self, mock_search: MagicMock) -> None:
        """--json/--csv flags persist parsed records to disk."""
        mock_search.return_value = [self.raw_uni]
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = str(Path(tmpdir) / "unis.json")
            csv_path = str(Path(tmpdir) / "unis.csv")
            stdout, _, code = self._run_cli(
                "--country", "Canada", "--json", json_path, "--csv", csv_path
            )
            self.assertIsNone(code)
            self.assertIn("records to JSON", stdout)
            self.assertIn("records to CSV", stdout)
            data = json.loads(Path(json_path).read_text(encoding="utf-8"))
            rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
        self.assertEqual(data[0]["primary_domain"], "utoronto.ca")
        self.assertEqual(rows[0]["country"], "Canada")


if __name__ == "__main__":
    unittest.main()
