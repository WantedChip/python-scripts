"""Unit tests for Exchange Rate Fetcher tool."""

import io
import json
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from main import convert_currency, fetch_exchange_rates, format_rate_table, main


def _fake_response(payload: Any, status: int = 200) -> MagicMock:
    """Build a context-manager mock for urlopen returning JSON payload."""
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.read.return_value = json.dumps(payload).encode("utf-8")
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_resp
    return mock_cm


class TestExchangeRateFetcher(unittest.TestCase):
    """Test suite for exchange rate fetcher functions."""

    @patch("urllib.request.urlopen")
    def test_fetch_exchange_rates_success(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_data = {
            "result": "success",
            "time_last_update_utc": "Fri, 24 Jul 2026 00:00:00 +0000",
            "base_code": "USD",
            "rates": {"EUR": 0.92, "GBP": 0.78, "JPY": 155.5},
        }
        mock_response.read.return_value = json.dumps(mock_data).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        data = fetch_exchange_rates("USD")
        self.assertEqual(data["base"], "USD")
        self.assertEqual(data["rates"]["EUR"], 0.92)

    @patch("urllib.request.urlopen")
    def test_fetch_historical_rates_uses_frankfurter(
        self, mock_urlopen: MagicMock
    ) -> None:
        """Historical queries hit the Frankfurter endpoint with the date."""
        mock_urlopen.return_value = _fake_response(
            {"date": "2026-01-02", "rates": {"USD": 1.04}}
        )
        data = fetch_exchange_rates("EUR", date="2026-01-02")
        self.assertEqual(data["date"], "2026-01-02")
        request = mock_urlopen.call_args[0][0]
        self.assertIn(
            "https://api.frankfurter.app/2026-01-02?from=EUR", request.full_url
        )

    @patch("urllib.request.urlopen")
    def test_fetch_api_error_payload_raises_value_error(
        self, mock_urlopen: MagicMock
    ) -> None:
        """API-reported failures surface as ValueError."""
        mock_urlopen.return_value = _fake_response(
            {"result": "error", "error-type": "unsupported-code"}
        )
        with self.assertRaisesRegex(ValueError, "unsupported-code"):
            fetch_exchange_rates("XYZ")

    @patch("urllib.request.urlopen")
    def test_fetch_missing_rates_raises_runtime_error(
        self, mock_urlopen: MagicMock
    ) -> None:
        """A 200 payload without rates is a runtime error."""
        mock_urlopen.return_value = _fake_response({"base_code": "USD"})
        with self.assertRaisesRegex(RuntimeError, "HTTP Error 200"):
            fetch_exchange_rates("USD")

    @patch("urllib.request.urlopen")
    def test_fetch_http_404_maps_to_value_error(self, mock_urlopen: MagicMock) -> None:
        """HTTP 404 indicates an invalid currency or date."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://api.frankfurter.app/bad?from=ZZZ",
            404,
            "Not Found",
            None,
            io.BytesIO(b"not found"),
        )
        with self.assertRaises(ValueError):
            fetch_exchange_rates("ZZZ", date="bad")

    @patch("urllib.request.urlopen")
    def test_fetch_http_500_raises_runtime_error(self, mock_urlopen: MagicMock) -> None:
        """Non-client HTTP errors raise RuntimeError."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://open.er-api.com/x",
            500,
            "Internal Server Error",
            None,
            io.BytesIO(b"oops"),
        )
        with self.assertRaisesRegex(RuntimeError, "HTTP Error 500"):
            fetch_exchange_rates("USD")

    @patch("urllib.request.urlopen")
    def test_fetch_url_error_raises_runtime_error(
        self, mock_urlopen: MagicMock
    ) -> None:
        """Network-level failures raise RuntimeError."""
        mock_urlopen.side_effect = urllib.error.URLError("connection refused")
        with self.assertRaisesRegex(RuntimeError, "Network error"):
            fetch_exchange_rates("USD")

    def test_convert_currency(self) -> None:
        rates_data = {"base": "USD", "rates": {"EUR": 0.90, "GBP": 0.80}}
        results = convert_currency(
            amount=100.0,
            base="USD",
            target_currencies=["EUR", "GBP"],
            rates_data=rates_data,
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["target"], "EUR")
        self.assertEqual(results[0]["converted_amount"], 90.0)

    def test_convert_currency_default_majors_skip_base_and_unknown(
        self,
    ) -> None:
        """Without targets, only known majors other than the base convert."""
        rates_data = {
            "base": "USD",
            "rates": {"USD": 1.0, "EUR": 0.9, "JPY": 155.0, "XXX": 5.0},
        }
        results = convert_currency(
            amount=10.0,
            base="USD",
            target_currencies=None,
            rates_data=rates_data,
        )
        targets = [r["target"] for r in results]
        self.assertEqual(targets, ["EUR", "JPY"])

    def test_convert_currency_skips_missing_targets(self) -> None:
        """Requested targets absent from the rate table are skipped."""
        results = convert_currency(
            amount=1.0,
            base="USD",
            target_currencies=["eur", "AUD"],
            rates_data={"base": "USD", "rates": {"EUR": 0.9}},
        )
        self.assertEqual([r["target"] for r in results], ["EUR"])
        self.assertEqual(results[0]["rate"], 0.9)

    def test_format_rate_table(self) -> None:
        conversions = [
            {
                "amount": 1.0,
                "base": "USD",
                "target": "EUR",
                "rate": 0.92,
                "converted_amount": 0.92,
            }
        ]
        table = format_rate_table(conversions, "USD", "2026-07-24")
        self.assertIn("Exchange Rates for USD", table)
        self.assertIn("EUR", table)

    def test_format_rate_table_empty(self) -> None:
        """Empty conversion sets render a friendly message."""
        table = format_rate_table([], "CHF", "2026-07-24")
        self.assertEqual(table, "No exchange rates found for base 'CHF'.")


class TestCli(unittest.TestCase):
    """CLI-level tests covering main() flows via sys.argv."""

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

    @staticmethod
    def _rates_payload() -> dict:
        """Return a representative successful rates payload."""
        return {
            "base": "USD",
            "date": "2026-07-24",
            "rates": {"EUR": 0.9, "GBP": 0.8},
        }

    @patch("main.fetch_exchange_rates")
    def test_cli_table_output(self, mock_fetch: MagicMock) -> None:
        """Default table output renders converted amounts."""
        mock_fetch.return_value = self._rates_payload()
        stdout, _, code = self._run_cli("-a", "100", "-t", "EUR,GBP")
        self.assertIsNone(code)
        self.assertIn("Exchange Rates for USD (Date/Updated: 2026-07-24)", stdout)
        self.assertIn("90.00 EUR", stdout)

    @patch("main.fetch_exchange_rates")
    def test_cli_json_output_to_file(self, mock_fetch: MagicMock) -> None:
        """--format json writes an export payload to the output file."""
        mock_fetch.return_value = self._rates_payload()
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = str(Path(tmpdir) / "rates.json")
            stdout, _, code = self._run_cli("-f", "json", "-o", out_path, "-t", "EUR")
            self.assertIsNone(code)
            self.assertIn("saved to", stdout)
            data = json.loads(Path(out_path).read_text(encoding="utf-8"))
        self.assertEqual(data["base"], "USD")
        self.assertEqual(data["conversions"][0]["target"], "EUR")

    @patch("main.fetch_exchange_rates")
    def test_cli_table_saved_to_txt_file(self, mock_fetch: MagicMock) -> None:
        """A .txt output file stores the rendered table text."""
        mock_fetch.return_value = self._rates_payload()
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = str(Path(tmpdir) / "rates.txt")
            _, _, code = self._run_cli("-o", out_path, "-t", "EUR")
            self.assertIsNone(code)
            content = Path(out_path).read_text(encoding="utf-8")
        self.assertIn("Exchange Rates for USD", content)

    @patch("main.fetch_exchange_rates")
    def test_cli_error_exits_one(self, mock_fetch: MagicMock) -> None:
        """Fetch failures print the error to stderr and exit 1."""
        mock_fetch.side_effect = RuntimeError("Network error: down")
        _, stderr, code = self._run_cli()
        self.assertEqual(code, 1)
        self.assertIn("Error: Network error: down", stderr)


if __name__ == "__main__":
    unittest.main()
