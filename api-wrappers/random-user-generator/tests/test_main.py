"""Unit tests for Random User Generator tool."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from main import export_csv, fetch_random_users, parse_user_profiles


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


if __name__ == "__main__":
    unittest.main()
