"""Unit tests for Cat Fact Fetcher."""

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
    accumulate_facts,
    fetch_cat_fact,
    load_existing_facts,
    main,
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


class TestNetworkErrorPaths(unittest.TestCase):
    """Tests for API failure handling in fetch_cat_fact."""

    @patch("main.urllib.request.urlopen")
    def test_fetch_cat_fact_request_failure(self, mock_urlopen: MagicMock) -> None:
        """Network failures are reported to stderr and mapped to None."""
        mock_urlopen.side_effect = urllib.error.URLError("dns failure")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.assertIsNone(fetch_cat_fact())
        self.assertIn("Error fetching cat fact", stderr.getvalue())

    @patch("main.urllib.request.urlopen")
    def test_fetch_cat_fact_strips_whitespace(self, mock_urlopen: MagicMock) -> None:
        """Surrounding whitespace is stripped from returned facts."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps(
            {"fact": "  Cats cannot taste sweetness.  "}
        ).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        self.assertEqual(fetch_cat_fact(), "Cats cannot taste sweetness.")

    @patch("main.urllib.request.urlopen")
    def test_fetch_cat_fact_missing_key(self, mock_urlopen: MagicMock) -> None:
        """Payloads without a fact key map to None."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"length": 0}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        self.assertIsNone(fetch_cat_fact())


class TestLoadExistingFacts(unittest.TestCase):
    """Tests for parsing the local facts collection file."""

    def test_missing_file_returns_empty(self) -> None:
        """A collection file that does not exist yields no facts."""
        self.assertEqual(load_existing_facts("no_such_file.json"), [])

    def test_md_numbered_star_and_plain_lines(self) -> None:
        """Markdown collections support bullets, numbers, and plain lines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "facts.md"
            file_path.write_text(
                "# Cat Facts Collection\n"
                "- Bullet fact\n"
                "* Star fact\n"
                "1. Numbered fact\n"
                "Plain fact\n",
                encoding="utf-8",
            )
            facts = load_existing_facts(str(file_path))
        self.assertEqual(
            facts, ["Bullet fact", "Star fact", "Numbered fact", "Plain fact"]
        )

    def test_corrupt_json_returns_empty_with_warning(self) -> None:
        """Unparseable JSON collections warn and yield no facts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "broken.json"
            file_path.write_text("{not valid json", encoding="utf-8")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                facts = load_existing_facts(str(file_path))
        self.assertEqual(facts, [])
        self.assertIn("Could not parse existing file", stderr.getvalue())

    def test_non_list_json_returns_empty(self) -> None:
        """JSON documents that are not lists yield no facts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "object.json"
            file_path.write_text(json.dumps({"fact": "x"}), encoding="utf-8")
            self.assertEqual(load_existing_facts(str(file_path)), [])


class TestSaveFailures(unittest.TestCase):
    """Tests for unwritable save targets."""

    def test_save_facts_json_oserror(self) -> None:
        """Unwritable JSON paths report failure instead of crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = str(Path(tmpdir) / "missing" / "facts.json")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                success = save_facts_json(["fact"], bad_path)
        self.assertFalse(success)
        self.assertIn("Error saving facts JSON", stderr.getvalue())

    def test_save_facts_md_oserror(self) -> None:
        """Unwritable Markdown paths report failure instead of crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = str(Path(tmpdir) / "missing" / "facts.md")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                success = save_facts_md(["fact"], bad_path)
        self.assertFalse(success)
        self.assertIn("Error saving facts Markdown", stderr.getvalue())


class TestAccumulateMarkdown(unittest.TestCase):
    """Tests for accumulating into a Markdown collection."""

    @patch("main.fetch_cat_fact")
    def test_accumulate_facts_md_collection(self, mock_fetch: MagicMock) -> None:
        """Fetching into a .md file appends numbered entries."""
        mock_fetch.return_value = "Cats cannot taste sweetness."
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = str(Path(tmpdir) / "collection.md")
            added, total = accumulate_facts(1, file_path)
            self.assertEqual(added, ["Cats cannot taste sweetness."])
            self.assertEqual(total, 1)
            content = Path(file_path).read_text(encoding="utf-8")
        self.assertIn("1. Cats cannot taste sweetness.", content)


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

    @patch("main.fetch_cat_fact")
    def test_cli_adds_and_reports_new_facts(self, mock_fetch: MagicMock) -> None:
        """Successful runs list each new fact and the collection total."""
        mock_fetch.side_effect = ["Fact one", "Fact two"]
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = str(Path(tmpdir) / "facts.json")
            stdout, _, code = self._run_cli("--count", "2", "--file", file_path)
            self.assertIsNone(code)
            self.assertIn("[1] Fact one", stdout)
            self.assertIn("[2] Fact two", stdout)
            self.assertIn("Total facts in collection: 2", stdout)

    @patch("main.fetch_cat_fact")
    def test_cli_no_new_facts_message(self, mock_fetch: MagicMock) -> None:
        """When nothing unique is fetched a warning is emitted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = str(Path(tmpdir) / "facts.json")
            save_facts_json(["Known fact"], file_path)
            mock_fetch.return_value = "Known fact"
            _, stderr, code = self._run_cli("--file", file_path)
            self.assertIsNone(code)
            self.assertIn("No new unique facts could be added", stderr)


if __name__ == "__main__":
    unittest.main()
