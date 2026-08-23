"""Unit tests for Random User Generator tool."""

import io
import json
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock, patch

from main import export_csv, fetch_random_users, main, parse_user_profiles


def _fake_response(payload: Any, status: int = 200) -> MagicMock:
    """Build a context-manager mock for urlopen returning JSON payload."""
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.read.return_value = json.dumps(payload).encode("utf-8")
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_resp
    return mock_cm


class TestRandomUserGenerator(unittest.TestCase):
    """Test suite for random user generator functions."""

    @patch("urllib.request.urlopen")
    def test_fetch_random_users_success(self, mock_urlopen: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_data = {
            "results": [
                {
                    "gender": "female",
                    "name": {"title": "Ms", "first": "Jane", "last": "Smith"},
                    "location": {
                        "street": {"number": 456, "name": "Oak Ave"},
                        "city": "London",
                        "state": "Greater London",
                        "country": "United Kingdom",
                        "postcode": "SW1A 1AA",
                    },
                    "email": "jane.smith@example.com",
                    "login": {"username": "janesmith"},
                    "dob": {"date": "1995-05-15T00:00:00.000Z", "age": 31},
                    "phone": "020-1234-5678",
                }
            ]
        }
        mock_response.read.return_value = json.dumps(mock_data).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        users = fetch_random_users(count=1, nationality="gb", gender="female")
        self.assertEqual(len(users), 1)

        profiles = parse_user_profiles(users)
        self.assertEqual(profiles[0]["full_name"], "Jane Smith")
        self.assertEqual(profiles[0]["email"], "jane.smith@example.com")
        self.assertEqual(profiles[0]["country"], "United Kingdom")

    def test_export_csv(self) -> None:
        profiles = [
            {
                "full_name": "Test User",
                "email": "test@example.com",
                "gender": "male",
                "age": 30,
            }
        ]

        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".csv") as tmp:
            tmp_path = Path(tmp.name)

        try:
            export_csv(profiles, tmp_path)
            content = tmp_path.read_text(encoding="utf-8")
            self.assertIn("full_name,email,gender,age", content)
            self.assertIn("Test User,test@example.com,male,30", content)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()


class TestFetchValidation(unittest.TestCase):
    """Tests for input validation and network error handling."""

    def test_count_below_one_raises(self) -> None:
        """Counts under 1 are rejected before any request is made."""
        with self.assertRaisesRegex(ValueError, "between 1 and 500"):
            fetch_random_users(count=0)

    def test_count_above_500_raises(self) -> None:
        """Counts over 500 are rejected before any request is made."""
        with self.assertRaisesRegex(ValueError, "between 1 and 500"):
            fetch_random_users(count=501)

    @patch("urllib.request.urlopen")
    def test_filters_and_seed_in_query_string(self, mock_urlopen: MagicMock) -> None:
        """Nationality, gender, and seed are encoded as query params."""
        mock_urlopen.return_value = _fake_response({"results": []})
        users = fetch_random_users(
            count=5, nationality="US,DE", gender="Male", seed=" reproducible "
        )
        self.assertEqual(users, [])
        request = mock_urlopen.call_args[0][0]
        self.assertIn("results=5", request.full_url)
        self.assertIn("nat=us%2Cde", request.full_url)
        self.assertIn("gender=male", request.full_url)
        self.assertIn("seed=reproducible", request.full_url)

    @patch("urllib.request.urlopen")
    def test_non_200_status_raises_runtime_error(self, mock_urlopen: MagicMock) -> None:
        """Unexpected HTTP statuses raise RuntimeError."""
        mock_urlopen.return_value = _fake_response({}, status=503)
        with self.assertRaisesRegex(RuntimeError, "HTTP Status 503"):
            fetch_random_users(count=1)

    @patch("urllib.request.urlopen")
    def test_http_error_wrapped_as_runtime_error(self, mock_urlopen: MagicMock) -> None:
        """HTTPError instances are wrapped as RuntimeError."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://randomuser.me/api/",
            429,
            "Too Many Requests",
            None,
            io.BytesIO(b"slow down"),
        )
        with self.assertRaisesRegex(RuntimeError, "HTTP Error 429"):
            fetch_random_users(count=1)

    @patch("urllib.request.urlopen")
    def test_url_error_wrapped_as_runtime_error(self, mock_urlopen: MagicMock) -> None:
        """Network failures are wrapped as RuntimeError."""
        mock_urlopen.side_effect = urllib.error.URLError("timed out")
        with self.assertRaisesRegex(RuntimeError, "Network error"):
            fetch_random_users(count=1)


class TestProfileParsing(unittest.TestCase):
    """Tests for raw-to-profile normalization."""

    def test_legacy_street_string_and_postcode_coercion(self) -> None:
        """String streets and numeric postcodes normalize correctly."""
        raw_user = {
            "name": {"title": "Mr", "first": "Zaphod"},
            "location": {
                "street": "12 Cosmic Lane",
                "city": "Beeblebrox",
                "postcode": 12345,
            },
            "dob": {"date": "1979-03-14T12:00:00.000Z", "age": 47},
        }
        profile = parse_user_profiles([raw_user])[0]
        self.assertEqual(profile["full_name"], "Zaphod")
        self.assertEqual(profile["street"], "12 Cosmic Lane")
        self.assertEqual(profile["postcode"], "12345")
        self.assertEqual(profile["dob"], "1979-03-14")

    def test_missing_fields_default_to_empty(self) -> None:
        """Sparse raw users produce empty-string placeholders."""
        profile = parse_user_profiles([{}])[0]
        self.assertEqual(profile["full_name"], "")
        self.assertEqual(profile["street"], "")
        self.assertEqual(profile["postcode"], "")
        self.assertIsNone(profile["age"])

    def test_export_csv_skips_empty_profiles(self) -> None:
        """Empty profile lists write no file at all."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "nested" / "users.csv"
            export_csv([], out_path)
            self.assertFalse(out_path.parent.exists())


class TestCli(unittest.TestCase):
    """CLI-level tests covering main() flows via sys.argv."""

    RAW_USERS = [
        {
            "gender": "male",
            "name": {"title": "Mr", "first": "John", "last": "Doe"},
            "location": {
                "street": {"number": 1, "name": "Main St"},
                "city": "Springfield",
                "state": "IL",
                "country": "United States",
                "postcode": 62704,
            },
            "email": "john.doe@example.com",
            "login": {"username": "jdoe"},
            "phone": "555-0100",
            "cell": "555-0199",
            "dob": {"date": "1980-01-01T00:00:00.000Z", "age": 46},
        }
    ]

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
    def _fetch_stub(tag: Optional[str] = None) -> Any:
        """Return a urlopen patcher yielding the shared sample payload."""
        return patch(
            "main.urllib.request.urlopen",
            return_value=_fake_response({"results": TestCli.RAW_USERS}),
        )

    @patch("main.fetch_random_users")
    def test_cli_json_stdout_and_file(self, mock_fetch: MagicMock) -> None:
        """JSON profiles print to stdout or save to a file."""
        mock_fetch.return_value = [dict(u) for u in self.RAW_USERS]
        stdout, _, code1 = self._run_cli("-n", "1")
        self.assertIsNone(code1)
        parsed = json.loads(stdout)
        self.assertEqual(parsed[0]["username"], "jdoe")

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = str(Path(tmpdir) / "sub" / "users.json")
            s2, _, code2 = self._run_cli("-n", "1", "-o", out_path)
            self.assertIsNone(code2)
            self.assertIn("Successfully generated and exported 1 profiles", s2)
            saved = json.loads(Path(out_path).read_text(encoding="utf-8"))
        self.assertEqual(saved[0]["email"], "john.doe@example.com")

    @patch("main.fetch_random_users")
    def test_cli_csv_stdout_and_file(self, mock_fetch: MagicMock) -> None:
        """CSV format writes to stdout without -o and to a file with it."""
        mock_fetch.return_value = [dict(u) for u in self.RAW_USERS]
        stdout, _, code1 = self._run_cli("-n", "1", "-f", "csv")
        self.assertIsNone(code1)
        flat = stdout.replace("\r\n", "\n")
        self.assertIn("last_name,full_name,gender,email", flat)
        self.assertIn("John Doe", flat)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = str(Path(tmpdir) / "users.csv")
            s2, _, code2 = self._run_cli("-n", "1", "-f", "csv", "-o", out_path)
            self.assertIsNone(code2)
            self.assertIn("exported 1 profiles", s2)
            content = Path(out_path).read_text(encoding="utf-8")
        self.assertIn("jdoe", content)

    def test_cli_invalid_count_exits_one(self) -> None:
        """Out-of-range counts print the error and exit 1."""
        _, stderr, code = self._run_cli("-n", "900")
        self.assertEqual(code, 1)
        self.assertIn("Error:", stderr)


if __name__ == "__main__":
    unittest.main()
