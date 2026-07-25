"""Unit tests for Cat Fact Fetcher."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from main import (
    accumulate_facts,
    fetch_cat_fact,
    load_existing_facts,
    save_facts_json,
    save_facts_md,
)


class TestCatFactFetcher(unittest.TestCase):
    """Test suite for cat fact fetcher functions."""

    def setUp(self) -> None:
        self.sample_fact_1 = "Cats sleep for 70% of their lives."
        self.sample_fact_2 = "A group of cats is called a clowder."

    @patch("main.urllib.request.urlopen")
    def test_fetch_cat_fact_success(self, mock_urlopen: MagicMock) -> None:
        """Test fetching a cat fact from API."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"fact": self.sample_fact_1}).encode(
            "utf-8"
        )
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        fact = fetch_cat_fact()
        self.assertEqual(fact, self.sample_fact_1)

    def test_save_and_load_facts_json(self) -> None:
        """Test saving and loading facts from JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = str(Path(tmpdir) / "facts.json")
            save_facts_json([self.sample_fact_1, self.sample_fact_2], file_path)

            loaded = load_existing_facts(file_path)
            self.assertEqual(len(loaded), 2)
            self.assertIn(self.sample_fact_1, loaded)

    def test_save_and_load_facts_md(self) -> None:
        """Test saving and loading facts from Markdown file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = str(Path(tmpdir) / "facts.md")
            save_facts_md([self.sample_fact_1, self.sample_fact_2], file_path)

            loaded = load_existing_facts(file_path)
            self.assertEqual(len(loaded), 2)
            self.assertIn(self.sample_fact_1, loaded)

    @patch("main.fetch_cat_fact")
    def test_accumulate_facts_deduplication(self, mock_fetch: MagicMock) -> None:
        """Test deduplicating facts against pre-existing items in file."""
        mock_fetch.side_effect = [self.sample_fact_1, self.sample_fact_2]
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = str(Path(tmpdir) / "facts.json")
            # Pre-seed file with fact 1
            save_facts_json([self.sample_fact_1], file_path)

            # Request 1 new fact
            added, total = accumulate_facts(1, file_path)

            self.assertEqual(added, [self.sample_fact_2])
            self.assertEqual(total, 2)


if __name__ == "__main__":
    unittest.main()
